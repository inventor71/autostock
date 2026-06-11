"""SteeringRuntime: assembles the F4 daemon-side engine and exposes daemon jobs.

Bundles channel + state + bus + coordinator + reconcile worker + command handler,
and provides the periodic jobs the scheduler drives: poll the file-drop channel,
publish the snapshot, drain off-hours trades at the open, and the ET-midnight sweep.
All broker access (commands + snapshot) runs on the single CommandBus worker
(NFR-2). Constructed only when steering is enabled; if absent, the daemon behaves
exactly as before (NFR-8).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from src.core.markettime import ET
from src.agent.steering.bus import CommandBus
from src.agent.steering.jsonl import atomic_write_text
from src.agent.steering.channel import SteeringChannel
from src.agent.steering.commands import CommandHandler
# F69: lightweight system-health publish (steering/health.json) for the TUI. The
# periodic daemon publish runs ONLY the cheap, no-external-call dimensions; the
# full 9-dimension deep check (broker/llm/account/risk live) stays in
# scripts/health.py for on-demand runs.
from src.monitoring.health import CheckerDispatcher
from src.monitoring.health.checker import BaseChecker
from src.monitoring.health.dimensions.config_env import ConfigEnvChecker
from src.monitoring.health.dimensions.logs import LogChecker
from src.monitoring.health.dimensions.process import ProcessChecker
from src.monitoring.health.dimensions.resources import ResourceChecker
from src.monitoring.health.report import CheckResult, CheckStatus, Severity
from config.config import get_settings
from src.agent.steering.records import EMERGENCY_VERBS
from src.agent.steering.security import (
    TOKEN_ENV_VAR,
    issue_token,
    write_agent_hook_settings,
)
from src.agent.steering.state import SteeringState
from src.agent.steering.turns import ReconcileWorker, TurnCoordinator

# repo root: src/agent/steering/runtime.py -> parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STEERING_DIR = _REPO_ROOT / "steering"


class _SnapshotAccountChecker(BaseChecker):
    """F69: the ``account`` health dimension derived from the daemon's last published
    snapshot — NO broker call. Distinct from the live ``AccountChecker`` (which queries
    the broker) used by scripts/health.py's full deep check. Registered alongside the
    cheap dimensions so the dispatcher assembles the report uniformly."""

    dimension = "account"

    def __init__(self, snapshot: dict | None):
        self._snapshot = snapshot

    def check(self) -> list[CheckResult]:
        snap = self._snapshot
        if not snap:
            return [CheckResult(
                name="account_snapshot",
                status=CheckStatus.SKIPPED,
                detail="No snapshot published yet (steering warming up)",
                severity=Severity.INFO,
            )]
        acct = snap.get("account") or {}
        market_open = snap.get("market_open")
        equity = acct.get("equity")
        cash = acct.get("cash")
        pos_n = acct.get("position_count")
        # Format the numeric line only when both fields are present — a partial
        # snapshot (equity but no cash, etc.) must not raise inside the f-string.
        if equity is not None and cash is not None:
            detail = (f"equity=${equity:,.0f} cash=${cash:,.0f} positions={pos_n} "
                      f"market={'OPEN' if market_open else 'CLOSED'}")
        else:
            detail = "snapshot present (account fields missing)"
        checks = [CheckResult(
            name="account_snapshot",
            status=CheckStatus.OK,
            detail=detail,
            severity=Severity.INFO,
        )]
        # Only an obviously broken account is a warning; this is a display check.
        if isinstance(cash, (int, float)) and cash < 0:
            checks.append(CheckResult(
                name="account_cash_negative",
                status=CheckStatus.WARNING,
                detail=f"cash is negative (${cash:,.0f})",
                severity=Severity.WARNING,
            ))
        return checks

def _resolve_code_version(root: Path) -> str:
    """The git HEAD SHA of the code THIS daemon process is running (F43 version-skew
    self-heal). Resolved ONCE at startup so it reflects the in-memory code, not a later
    merge to the working tree. Stamped into every snapshot; the ``autostock`` launcher
    compares it against the working-tree HEAD and restarts a daemon left running stale
    code (which silently rejects new console verbs, e.g. F38 ``research``). Any failure
    (no git / not a repo) -> ``""``; NEVER raises (a missing stamp must not break boot).
    The launcher treats a present-but-blank stamp as 'unknown' (fail-open, no restart),
    so a daemon that simply can't reach git does not trigger a restart loop."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root), capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


# F25: US equity market-session rule (wall-clock ET). DST is resolved by the TUI
# using the IANA tz, so only fixed wall times live here.
_DEFAULT_MARKET_RULE = {
    "tz": "America/New_York",
    "pre_open": "04:00",
    "regular_open": "09:30",
    "regular_close": "16:00",
    "after_close": "20:00",
}


class SteeringRuntime:
    def __init__(self, executor, orchestrator, *, steering_dir: str | Path | None = None,
                 token: str | None = None):
        self.executor = executor
        self.orchestrator = orchestrator
        self.steering_dir = Path(steering_dir) if steering_dir else DEFAULT_STEERING_DIR
        # Honor a pre-set STEERING_OPERATOR_TOKEN (from .env / the daemon's shell) so the
        # SEPARATELY-launched console can share ONE secret with the daemon; only generate a
        # random one when none is provided. (Previously this always generated a random token
        # and start() overwrote the env value -> the console's token never matched -> the
        # channel rejected every command as "bad token" -> end-to-end steering silently failed.)
        # session._invoke still scrubs this var from the AGENT's env (BR-10.2).
        self.token = token or os.environ.get(TOKEN_ENV_VAR) or issue_token()
        self.channel = SteeringChannel(self.steering_dir, self.token)
        self.state = SteeringState(executor.journal.root)
        self.bus = CommandBus()
        self.coordinator = TurnCoordinator()
        self.reconcile_worker = ReconcileWorker(self.coordinator)
        self.handler = CommandHandler(
            self.channel, self.state, executor,
            reconcile_worker=self.reconcile_worker, reconcile_run_fn=self._reconcile_run_fn,
            turn_trigger_fn=self._trigger_turn,
        )
        self._pushed_questions: set[str] = set()
        # F3: in-proc snapshot cache (critic#4) so the BriefAssembler/WakeDetector
        # read the latest published view from memory, not by re-parsing the file.
        self.last_snapshot: dict | None = None
        # F3: broker fill-event cursor (Q3=A) advanced on the bus worker. Persisted
        # so a restart resumes; on first ever run we start "now" so the daemon does
        # NOT wake on the whole history of fills.
        self._fills_cursor_file = Path(executor.journal.root) / ".fills.cursor"
        self._fills_cursor = self._load_fills_cursor()
        self._seen_fill_ids: set[str] = set()
        # F22: current in-flight turn (set by modes/agent before the LLM call,
        # cleared in the finally block). Published in monitor.json so the TUI
        # can show "turn in progress" state.
        self._current_turn: dict | None = None
        # F6: latest today's-round-trip summary, refreshed on a slow cadence by
        # refresh_round_trip() (one broker get_fills call) and folded into the snapshot
        # by publish_snapshot — keeping snapshot.json single-writer while the network
        # fills call runs far less often than the 5s snapshot publish.
        self._round_trip: dict = {}
        # F8: sidebar enrichment caches, filled by slow-cadence worker jobs and
        # folded into the snapshot by publish_snapshot (keeps snapshot.json a
        # single writer, NFR-2). PriceBook = current price of resting-order
        # symbols we don't hold (held symbols reuse position.current_price).
        self._price_book: dict[str, tuple[float, datetime]] = {}
        self._recent_fills: list[dict] = []
        # F25: market-session rule published in monitor.json so the TUI renders a
        # market-aware 12h timeline. Wall-clock ET times (DST handled by the TUI's
        # IANA tz conversion). Overridable via set_market_rule() from settings.
        self._market_rule: dict = dict(_DEFAULT_MARKET_RULE)
        # F43: git HEAD SHA of the code this process loaded (resolved once at boot).
        # Stamped into every snapshot so the launcher can detect a daemon left running
        # stale code after a merge and auto-restart it (version-skew self-heal).
        self._code_version: str = _resolve_code_version(_REPO_ROOT)

    def _load_fills_cursor(self) -> str:
        try:
            if self._fills_cursor_file.exists():
                return self._fills_cursor_file.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning("fills cursor load failed: {}", e)
        return datetime.now(timezone.utc).isoformat()

    # ---- lifecycle -------------------------------------------------------- #
    def start(self) -> None:
        # Publish the token to THIS process's env so a child operator tool (Unit B)
        # inherits it out-of-band; it is scrubbed from the agent's env on spawn
        # (session._invoke -> scrub_agent_env). Never written to a file / logged.
        os.environ[TOKEN_ENV_VAR] = self.token
        write_agent_hook_settings(self.executor.journal.root)  # BR-10.1 confinement
        self.bus.start()
        # F29: publish the project directory tree so the supervisor agent can
        # discover the repo structure without guessing file paths.
        self._publish_codebase_tree()
        logger.info("Steering runtime started (channel={}, hook installed)", self.steering_dir)

    def stop(self) -> None:
        self.reconcile_worker.stop()
        self.bus.stop()

    # ---- reconcile -------------------------------------------------------- #
    def _reconcile_run_fn(self):
        return self.orchestrator.run_reconcile(self._recent_context())

    # ---- manual turn trigger (F38) ---------------------------------------- #
    def _trigger_turn(self, kind: str, corr_id: str) -> str:
        """Start a named turn on demand (human steering verb). Off-thread via the
        coordinator so the CommandBus worker is not blocked for the turn's duration.
        Top priority + never dropped (F38): a deliberate human command must not be
        bumped by an automatic scheduled/wake/reconcile turn, so it queues for the
        lock instead of skipping. Returns "started" (ran now) or "queued" (runs after
        the in-flight turn). Only "research" is supported for now (F38 D1).

        F44: if a turn of the same ``kind`` is already running (the in-flight turn,
        auto or manual) or already queued, it is NOT re-queued — returns
        "already_running" / "already_queued" so the operator is told it is already in
        progress instead of stacking a duplicate.

        On completion an outcome event correlated to ``corr_id`` (the triggering
        command) is published so the operator gets a result report without polling:
        ``completed`` with the decision counts, or ``failed`` with the error. The
        emit is enqueued on the CommandBus worker (channel writes belong there), not
        done on the turn thread."""
        import time

        run_fns = {"research": self.orchestrator.run_morning_research}
        run_fn = run_fns.get(kind)
        if run_fn is None:
            return "unknown_turn"
        started = time.monotonic()

        def _on_done(_result, error) -> None:
            elapsed = time.monotonic() - started
            if error is not None:
                outcome, detail = "failed", f"{kind} turn failed: {error} ({elapsed:.0f}s)"
            else:
                n = len(self.orchestrator.last_new_decisions)
                kept = len(self.orchestrator.last_kept)
                detail = (f"{kind} turn complete: {n} decision(s), {kept} in-universe "
                          f"({elapsed:.0f}s)")
                outcome = "completed"
            # channel writes happen on the bus worker (single-writer invariant).
            self.bus.submit(lambda: self.channel.emit_outcome(corr_id, outcome, detail))

        # F44 dedup: the in-flight turn's type (set for every turn via _on_turn_start)
        # is the "running" key — covers the auto premarket research turn too, so a
        # manual /research fired while research is already running is rejected, not queued.
        running_key = (self._current_turn or {}).get("type")
        return self.coordinator.start_priority_async(
            run_fn, kind=f"manual_{kind}", on_done=_on_done,
            dedup_key=kind, running_key=running_key)

    def _recent_context(self) -> str:
        directives = "; ".join(d.text for d in self.state.active_directives()) or "none"
        log = self.executor.journal.root / "human_directives.jsonl"
        recent = ""
        if log.exists():
            recent = "\n".join(log.read_text(encoding="utf-8").splitlines()[-8:])
        return f"Active directives: {directives}\nRecent interventions:\n{recent}"

    # ---- scheduler jobs --------------------------------------------------- #
    def poll_commands(self) -> None:
        """Read new file-drop commands and enqueue each on the worker (emergency
        verbs to the emergency lane). Best-effort: never raise into the scheduler."""
        try:
            for cmd in self.channel.read_new_commands():
                emergency = cmd.verb in EMERGENCY_VERBS
                self.bus.submit(lambda c=cmd: self.handler.handle(c), emergency=emergency)
        except Exception as e:
            logger.error("steering poll failed (continuing): {}", e)

    def publish_snapshot(self) -> None:
        """Publish the live read view. Broker access runs on the worker (NFR-2).

        F3: also collects *new* fill events (broker activities cursor) into the
        payload for the new-fill wake, and mirrors the published dict into
        ``self.last_snapshot`` so off-thread readers (BriefAssembler/WakeDetector)
        never re-parse the file or touch the broker (critic#3/#4)."""
        def _build():
            broker = self.executor.broker
            try:
                ps = broker.get_portfolio_state()
                # F54: include side so the TUI can mark long vs short (L/S) and
                # render a short's price-down-is-profit coloring correctly.
                positions = {s: {"qty": p.qty, "avg_entry_price": p.avg_entry_price,
                                 "side": getattr(getattr(p, "side", None), "value", "long"),
                                 "current_price": p.current_price,
                                 "market_value": p.market_value,
                                 "unrealized_pnl": p.unrealized_pnl}
                             for s, p in ps.positions.items()}
                # F8: current price per resting order. Held symbols reuse the
                # position price (no extra call); order-only symbols come from the
                # PriceBook cache (slow job). Missing -> None (sidebar blanks Δ).
                held_prices = {s: p.current_price for s, p in ps.positions.items()}
                opens = [{"symbol": o.symbol, "order_id": o.order_id,
                          "stop_price": o.stop_price, "limit_price": o.limit_price,
                          "side": getattr(o.side, "value", o.side),
                          "order_type": getattr(o.order_type, "value", o.order_type),
                          "current_price": held_prices.get(o.symbol)
                          or self._price_book_get(o.symbol)}
                         for o in broker.get_open_orders()]
                market_open = broker.is_market_open()
            except Exception as e:
                logger.warning("snapshot build failed (skipping): {}", e)
                return
            new_fills = self._collect_new_fills(broker)
            snapshot = {
                "run_state": self.state.run_state().model_dump(mode="json"),
                "locked_symbols": {s: self.state.lock_status(s) for s in positions},
                "pending": [p.model_dump(mode="json") for p in self.state.list_pending()],
                "positions": positions,
                "open_orders": opens,
                "fills": [f.model_dump(mode="json") for f in new_fills],
                "queued_trades": [
                    {"id": c.id, "verb": c.verb,
                     "args": {k: v for k, v in c.args.items() if k != "raw"},
                     "ts": c.ts.isoformat()}
                    for c in self.channel.list_offhours()
                ],
                "market_open": market_open,
                "account": self._account_block(ps),  # F6 FR-2 (reuses equity_log.snapshot)
                "round_trip": self._round_trip,       # F6 FR-3 (cached, slow-cadence refresh)
                "recent_fills": self._recent_fills,   # F8 FR-3 (cached, slow-cadence refresh)
                "code_version": self._code_version,   # F43: launcher version-skew self-heal
            }
            self.last_snapshot = snapshot
            self.channel.publish_snapshot(snapshot)
        self.bus.submit(_build)

    def _collect_new_fills(self, broker) -> list:
        """Return fill events not yet seen, advancing the persisted cursor.

        Idempotent by activity id: the cursor is the max ``transaction_time``
        seen, and ``_seen_fill_ids`` retains only ids at that boundary timestamp
        (which ``after=cursor`` may re-return). Best-effort (NFR-4)."""
        try:
            fills = broker.get_fills(since=self._fills_cursor)
            if not fills:
                return []
            new = [f for f in fills if f.fill_id not in self._seen_fill_ids]
            cursor = max(f.ts for f in fills).isoformat()
            self._fills_cursor = cursor
            self._seen_fill_ids = {f.fill_id for f in fills if f.ts.isoformat() == cursor}
        except Exception as e:
            # Never abort the snapshot publish over fill detection (NFR-4); the
            # cursor simply doesn't advance and the next tick retries.
            logger.warning("new-fill detection failed (skipping): {}", e)
            return []
        try:
            atomic_write_text(self._fills_cursor_file, cursor)
        except Exception as e:
            logger.warning("fills cursor persist failed: {}", e)
        return new

    def drain_offhours(self) -> None:
        """At the open: enqueue any off-hours trades queued overnight (BR-2.7)."""
        for cmd in self.channel.drain_offhours():
            self.bus.submit(lambda c=cmd: self.handler.handle(c))

    def poll_agent_questions(self) -> None:
        """FR-7: push newly-appended agent questions to the operator as events.
        Reads the agent-written file torn-safely; never rewrites it (critic #7)."""
        from src.agent.steering.jsonl import read_complete_lines
        from src.agent.steering.records import AgentQuestion, SteeringEvent

        path = self.executor.journal.root / "agent_questions.jsonl"
        try:
            lines, _ = read_complete_lines(path, 0)
            for line in lines:
                try:
                    q = AgentQuestion.model_validate_json(line)
                except Exception:
                    continue
                if q.id in self._pushed_questions:
                    continue
                self._pushed_questions.add(q.id)
                self.channel.append_event(SteeringEvent(
                    kind="agent_question",
                    payload={"id": q.id, "symbol": q.symbol, "text": q.text}))
        except Exception as e:
            logger.error("steering agent-question poll failed (continuing): {}", e)

    def daily_sweep(self) -> None:
        """ET-midnight: clear past-day locks/pending + re-scope channel (BR-4.8/critic #4)."""
        self.state.sweep_expired()
        self.channel.daily_reset()
        self._pushed_questions.clear()

    # ---- F6: account / round-trip / monitor read views -------------------- #
    @staticmethod
    def _account_block(ps) -> dict:
        """F6 FR-2: compact account summary. Reuses equity_log.snapshot (critic #5)
        so the sidebar and the equity track record never diverge."""
        from src.agent.equity_log import snapshot as equity_snapshot
        full = equity_snapshot(ps)
        return {k: full[k] for k in ("equity", "cash", "invested", "open_pnl", "position_count")}

    def refresh_round_trip(self, *, since: str | None = None) -> None:
        """F6 FR-3: refresh today's round-trip summary from the broker's live fills
        on the worker (NFR-2). Reuses F3's get_fills (FillEvent stream) — trades.jsonl
        is EOD-only, so a file read would be empty intraday. Slow cadence (one network
        call); publish_snapshot folds the cached result in at its own rate. Best-effort."""
        from src.core.trades import summarize_today_round_trips

        def _build():
            try:
                fills = self.executor.broker.get_fills(since=since)
                dicts = [
                    {"symbol": f.symbol, "side": f.side, "qty": f.qty,
                     "price": f.price, "ts": f.ts.isoformat()}
                    for f in fills
                ]
                self._round_trip = summarize_today_round_trips(dicts, now_et=datetime.now(ET))
            except Exception as e:
                logger.warning("round-trip refresh failed (skipping): {}", e)
        self.bus.submit(_build)

    # ---- F8: sidebar price / recent-fills enrichment (slow-cadence jobs) --- #
    _PRICE_TTL_SEC = 30
    _RECENT_FILLS = 8

    def _price_book_get(self, symbol: str) -> float | None:
        """Fresh cached price for an order-only symbol, else None (Δ blank)."""
        entry = self._price_book.get(symbol)
        if not entry:
            return None
        price, fetched_at = entry
        if (datetime.now(timezone.utc) - fetched_at).total_seconds() > self._PRICE_TTL_SEC:
            return None
        return price

    def refresh_order_prices(self) -> None:
        """F8 FR-2: fill in current prices for resting-order symbols we don't
        hold (held symbols already carry current_price). Worker job, best-effort
        (NFR-4); only fetches symbols missing/stale in the cache."""
        def _build():
            try:
                broker = self.executor.broker
                ps = broker.get_portfolio_state()
                held = set(ps.positions)
                order_syms = {o.symbol for o in broker.get_open_orders()}
                missing = [s for s in order_syms - held if self._price_book_get(s) is None]
                if not missing:
                    return
                now = datetime.now(timezone.utc)
                for sym, px in broker.get_latest_prices(missing).items():
                    self._price_book[sym] = (px, now)
            except Exception as e:
                logger.warning("order-price refresh failed (skipping): {}", e)
        self.bus.submit(_build)

    def refresh_recent_fills(self) -> None:
        """F8 FR-3: cache the most recent fills (what was bought/sold) for the
        sidebar. Reuses get_fills (F3/F6 FillEvent stream). Worker job, best-effort."""
        def _build():
            try:
                fills = self.executor.broker.get_fills()
                fills = sorted(fills, key=lambda f: f.ts, reverse=True)[: self._RECENT_FILLS]
                self._recent_fills = [
                    {"ts": f.ts.isoformat(), "side": f.side, "qty": f.qty,
                     "symbol": f.symbol, "price": f.price}
                    for f in fills
                ]
            except Exception as e:
                logger.warning("recent-fills refresh failed (skipping): {}", e)
        self.bus.submit(_build)

    def set_current_turn(self, turn_id: str, turn_type: str) -> None:
        self._current_turn = {
            "id": turn_id, "type": turn_type,
            # F25: tz-aware ISO so the TUI localizes (was %H:%M, losing date/tz).
            "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }

    def clear_current_turn(self) -> None:
        self._current_turn = None

    def set_market_rule(self, rule: dict | None) -> None:
        """F25: override the published market-session rule (from settings)."""
        if rule:
            self._market_rule = {**_DEFAULT_MARKET_RULE, **rule}

    def _session_et_date(self) -> str:
        """F25: the ET trading date the timeline should default to — the live
        session during extended hours on a weekday, else the next weekday."""
        return _resolve_session_et_date(self._market_rule)

    # F29: project directory tree for supervisor orientation ------------------ #
    # Scanned once at startup; source structure doesn't change while the daemon
    # runs. Descriptions are hand-maintained (structural changes are rare, and
    # human intent matters more than auto-extracted docstrings).

    _TREE_DIRS = ["src", "operator-console", "config", "tests", "docs", "scripts"]
    _TREE_EXCLUDE = {"__pycache__", ".git", "node_modules", ".mypy_cache",
                     ".pytest_cache", ".ruff_cache", "venv", ".venv",
                     "dist", "build", ".DS_Store"}
    # Glob-style patterns checked via fnmatch (egg-info dirs vary by project name).
    _TREE_EXCLUDE_GLOBS = ["*.egg-info"]

    @classmethod
    def _is_excluded(cls, name: str) -> bool:
        """True when *name* should be excluded from the codebase tree."""
        if name in cls._TREE_EXCLUDE:
            return True
        return any(fnmatch.fnmatch(name, pat) for pat in cls._TREE_EXCLUDE_GLOBS)

    _PKG_DESCRIPTIONS: dict[str, str] = {
        "src": "Python application code",
        "src/agent": "Agent mode — LLM PM + journal + decision executor + steering engine",
        "src/agent/intraday": "F3 — real-time wake detection / brief assembly / abnormal-move",
        "src/agent/steering": "F4 — operator steering engine (bus/turns/state/channel/commands)",
        "src/agent/tools": "Agent MCP tools (market data, account, news, watch)",
        "src/trading": "Trading engine + mode dispatch (agent/paper/live/backtest)",
        "src/trading/modes": "Per-mode entry points (agent.py, paper.py, backtest.py)",
        "src/strategy": "Strategy implementations",
        "src/strategy/technical": "Technical strategies — MA Crossover, RSI, MACD, Bollinger",
        "src/strategy/ml": "ML strategies — Random Forest, LSTM",
        "src/strategy/llm": "LLM strategy (Claude/OpenAI) + prompt auto-improvement",
        "src/risk": "Risk management — single order gate (manager.py) + exits + sizing",
        "src/execution": "Broker abstraction — BaseBroker, SimulatedBroker, AlpacaBroker",
        "src/data": "Data collection / transformation (yfinance, Alpaca, intraday features)",
        "src/core": "Shared Pydantic models / types / enums (depended on by all, depends on none)",
        "src/config": "Configuration (pydantic-settings, settings.yaml loader)",
        "operator-console": "Operator console — opencode hard-fork (TypeScript)",
        "operator-console/cli": "opencode fork — TUI + permission engine + agent session",
        "operator-console/launcher": "autostock launcher — config resolution + process management",
        "operator-console/src": "MCP server (mcp-server.ts) + steer handler + file-drop client",
        "config": "YAML configuration files (settings.yaml, strategies.yaml)",
        "tests": "Python test suite",
        "docs": "Design documentation (DESIGN.md)",
        "scripts": "Utility scripts (agent_trace.py, worktree-setup.sh, etc.)",
        "workspace": "Agent runtime data — journal, turns, decisions, human directives",
        "steering": "Operator steering channel — snapshot.json, monitor.json, commands, events",
        "aidlc-docs": "AI-DLC design documents — requirements, plans, track records, RE artifacts",
        "logs": "Daemon log output (autostock.log)",
    }

    _KEY_FILES: dict[str, str] = {
        "src/agent/orchestrator.py": "AgentTradingLoop — sequences research/intraday/EOD turns",
        "src/agent/session.py": "AgentSession — wraps claude CLI subprocess",
        "src/agent/executor.py": "DecisionExecutor — decisions→orders (the only order-placing path)",
        "src/agent/journal.py": "File-based journal (workspace/decisions.jsonl)",
        "src/agent/prompts.py": "LLM prompt templates (research / intraday / EOD / wake)",
        "src/agent/review.py": "EOD self-review → lessons learned",
        "src/trading/engine.py": "TradingEngine — strategy-path per-symbol cycle",
        "src/trading/modes/agent.py": "AgentTradingMode — daemon scheduler setup for agent mode",
        "src/risk/manager.py": "RiskManager — single gate: signal/decision → Order",
        "src/execution/base.py": "BaseBroker — abstract broker; SimulatedBroker, AlpacaBroker",
        "src/execution/alpaca_broker.py": "AlpacaBroker — live Alpaca Trading API",
        "src/data/intraday/features.py": "Per-session intraday features (F1)",
        "src/core/models.py": "Core Pydantic models — Order, Position, PortfolioState, etc.",
        "operator-console/src/mcp-server.ts": "MCP server — steer/steer_read + Alpaca-shaped tools",
        "operator-console/src/steer-handler.ts": "steer/steer_read command dispatch + validation",
        "operator-console/launcher/config.ts": "Launcher config — env resolution + permission profiles",
        "config/settings.yaml": "Main settings — universe, risk, intraday, agent config",
        "main.py": "CLI entry point — mode dispatch (agent/backtest/paper/live)",
    }

    def _publish_codebase_tree(self, root: Path | None = None) -> None:
        """Generate the project directory tree and publish it via the channel.

        Scanned once at daemon start; the tree is small enough to serve inline
        via ``steer_read{command:/codebase}``.  Excludes build artifacts, caches,
        and virtual environments so the output stays focused on source layout.

        *root* defaults to ``_REPO_ROOT``; override for testing against a
        synthetic tree."""
        root = root or _REPO_ROOT
        lines = [f"{{AUTOSTOCK_ROOT}} = {root}", ""]
        # Walk depth-first, three levels (root files/dirs → src/ packages → sub-packages).
        for entry in sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name)):
            if entry.name.startswith(".") or self._is_excluded(entry.name):
                continue
            if entry.is_dir():
                desc = self._PKG_DESCRIPTIONS.get(entry.name, "")
                lines.append(f"{entry.name}/" + (f"  # {desc}" if desc else ""))
                if entry.name in self._TREE_DIRS:
                    self._walk_tree(entry, entry.name, lines, depth=2, indent=1)
            else:
                desc = self._KEY_FILES.get(entry.name, "")
                lines.append(f"{entry.name}" + (f"  # {desc}" if desc else ""))
        # Append the steering/ + workspace/ + aidlc-docs/ + logs/ dirs at root
        # level since they are outside _TREE_DIRS but useful to know about.
        for extra in ["workspace", "steering", "aidlc-docs", "logs"]:
            if extra not in self._TREE_DIRS:
                ep = root / extra
                if ep.is_dir():
                    desc = self._PKG_DESCRIPTIONS.get(extra, "Runtime / design data")
                    lines.append(f"{extra}/  # {desc}")
        tree_text = "\n".join(lines)
        try:
            self.channel.publish_codebase(tree_text)
        except Exception as e:
            logger.warning("codebase tree publish failed (non-fatal): {}", e)

    def _walk_tree(self, directory: Path, prefix: str, lines: list[str],
                   depth: int, indent: int = 1) -> None:
        """Recurse into *directory*, appending indented entries to *lines*.

        *indent* grows with each recursion level so the visual hierarchy is
        preserved in the output."""
        if depth <= 0:
            return
        pad = "  " * indent
        entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        for entry in entries:
            if entry.name.startswith(".") or self._is_excluded(entry.name):
                continue
            rel = f"{prefix}/{entry.name}"
            if entry.is_dir():
                desc = self._PKG_DESCRIPTIONS.get(rel, "")
                lines.append(f"{pad}{entry.name}/" + (f"  # {desc}" if desc else ""))
                if depth > 1:
                    self._walk_tree(entry, rel, lines, depth - 1, indent + 1)
            else:
                desc = self._KEY_FILES.get(rel, "")
                if desc:
                    lines.append(f"{pad}{entry.name}  # {desc}")

    def publish_monitor(self) -> None:
        """F6 FR-4 / F22: publish structured turns / decisions / agent-log
        summaries to steering/monitor.json. F22 changes: turns.recent and
        decisions are now structured objects (not strings), and current_turn
        shows the in-flight turn. Files only — no broker access."""
        try:
            root = self.executor.journal.root
            # F44: count of manual turns waiting for the lock (excludes the in-flight
            # one) — backs the TUI progress label's "+N queued".
            running_key = (self._current_turn or {}).get("type")
            payload = {
                "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                "current_turn": self._current_turn,
                "queued": len(self.coordinator.queued_kinds(running_key)),
                "workspace_root": str(root),
                # F25: market-aware timeline metadata.
                "market": self._market_rule,
                "session_et_date": self._session_et_date(),
                "turns": _turns_summary(root / "turns.jsonl"),
                "decisions": _decisions_tail(root / "decisions.jsonl",
                                             root / "turns.jsonl"),
                "interventions": _interventions_tail(root / "human_directives.jsonl",
                                                    self._session_et_date()),
                "log": _log_tail(_REPO_ROOT / "logs" / "autostock.log"),
            }
            atomic_write_text(self.steering_dir / "monitor.json", json.dumps(payload, default=str))
        except Exception as e:
            logger.error("steering monitor publish failed (continuing): {}", e)

    def publish_health(self) -> None:
        """F69: publish a lightweight system-health report to steering/health.json.

        Runs ONLY the cheap, no-external-call dimensions (process / logs / config_env
        / resources) and derives an ``account`` dimension from the snapshot the daemon
        already holds (``self.last_snapshot``) — so a 5-minute cadence costs no broker
        creation, no LLM API ping, and no extra network I/O. The full 9-dimension deep
        check (which DOES create brokers and ping the LLM) stays in scripts/health.py.

        Runs on a scheduler thread-pool worker (NFR-1): does not block the 2s command
        poll or the trade bus. Best-effort — a failure keeps the previous health.json.
        """
        try:
            settings = get_settings()
            # Inject the repo root explicitly. Without it the checkers fall back to
            # BaseChecker.root (derived from the health module's own path), which from a
            # worktree resolves ABOVE the checkout — making config_env/process/resources
            # all fail and the report a permanent false CRITICAL.
            dispatcher = CheckerDispatcher(settings, project_root=_REPO_ROOT)
            dispatcher.register_all([
                ProcessChecker(settings),
                LogChecker(settings),
                ConfigEnvChecker(settings),
                ResourceChecker(settings),
                # `account` is just another checker — fed the snapshot the daemon
                # already holds, so the dispatcher assembles dimensions + overall +
                # summary uniformly (no hand-rolled report mutation).
                _SnapshotAccountChecker(self.last_snapshot),
            ])
            report = dispatcher.run()
            payload = report.model_dump(mode="json")
            # F69: stamp the publish cadence so the TUI can compute "stale" without
            # hardcoding an interval that drifts from health_publish_seconds.
            payload["publish_interval_seconds"] = settings.monitoring.health_publish_seconds
            atomic_write_text(self.steering_dir / "health.json", json.dumps(payload, default=str))
        except Exception as e:
            logger.warning("steering health publish failed (keeping last health.json): {}", e)


# ---- monitor.json helpers (F6 FR-4) ------------------------------------- #
# File-only, defensive, read-only. Build the deep-monitoring view (turn telemetry /
# recent decisions / agent log tail) the operator pulls on demand via steer_read{view}.

_MONITOR_TURNS = 50
_MONITOR_DECISIONS = 20
_MONITOR_LOG = 30
# Redact obvious secrets from the log tail (SECURITY-03): the value after a
# token/key/secret key, and any long opaque hex/base64 run.
_SECRET_KV = re.compile(r"(?i)\b(token|secret|api[_-]?key|password|authorization)\b\s*[=:]\s*\S+")
_SECRET_BLOB = re.compile(r"\b[A-Za-z0-9_\-]{24,}\b")


def _hhmm(ts) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(str(ts)).strftime("%H:%M")
    except (ValueError, TypeError):
        return str(ts)[11:16]


def _iso(ts) -> str:
    """F25: forward a full tz-aware ISO timestamp. A naive value is localized so
    the TUI can convert to the operator's timezone."""
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(str(ts))
    except (ValueError, TypeError):
        return str(ts)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.isoformat(timespec="seconds")


def _resolve_session_et_date(rule: dict | None = None) -> str:
    """The ET trading date the timeline defaults to: the live session during
    extended hours on a weekday, otherwise the next weekday (Q8=A — holidays
    just render an empty bar, so a plain weekday roll is sufficient)."""
    rule = rule or _DEFAULT_MARKET_RULE
    now_et = datetime.now(ET)
    pre = _parse_hhmm(rule.get("pre_open", "04:00"))
    after = _parse_hhmm(rule.get("after_close", "20:00"))
    in_session = (now_et.weekday() < 5) and (pre <= (now_et.hour * 60 + now_et.minute) < after)
    if in_session:
        return now_et.date().isoformat()
    d = now_et.date()
    # roll forward to the next weekday session (today if still upcoming pre-open)
    if now_et.weekday() < 5 and (now_et.hour * 60 + now_et.minute) < pre:
        return d.isoformat()
    while True:
        d = d.fromordinal(d.toordinal() + 1)
        if d.weekday() < 5:
            return d.isoformat()


def _parse_hhmm(s: str) -> int:
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


# F25: human steering verbs that count as trade interventions (Q5=A). Lifecycle/
# note/approval verbs are excluded from the timeline.
_TRADE_VERBS = {
    "buy", "sell", "short", "cover", "flatten", "flatten_all", "place_order",
    "cancel", "cancel_order", "cancel_all", "close_position", "close_all",
}
_MONITOR_INTERVENTIONS = 50


def _interventions_tail(path: Path, et_date: str | None = None) -> list[dict]:
    """F25 FR-3: trade-only human interventions for the timeline, read from
    human_directives.jsonl (InterventionRecord). Read-only; no broker access.

    When *et_date* is given, scans backwards from the end, collecting up to
    _MONITOR_INTERVENTIONS entries that match the date and stopping at the
    first entry from a different date (lines are roughly chronological).
    This replaces the old fixed 150-line window that silently dropped older
    same-day interventions as the file grew (F32 bugfix)."""
    from src.agent.turn_log import compute_et_date
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        logger.warning("interventions read failed (skipping): {}", e)
        return []
    # F32: when a target ET date is given, scan backwards until we have enough
    # matches or hit a different date. Otherwise keep the legacy full-scan cap.
    if et_date is not None:
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            verb = str(r.get("command") or "")
            if verb not in _TRADE_VERBS:
                continue
            ts = r.get("ts")
            entry_et = compute_et_date(ts)
            if entry_et != et_date:
                continue
            out.append({
                "ts": _iso(ts),
                "et_date": entry_et,
                "verb": verb,
                "symbol": _intervention_symbol(verb, r.get("args") or {}),
                "outcome": _mask_secrets(str(r.get("outcome", ""))),
                "detail": _mask_secrets(str(r.get("detail", ""))),
            })
            if len(out) >= _MONITOR_INTERVENTIONS:
                break
        out.reverse()  # restore chronological order
        return out
    # Legacy: no target date — scan last _MONITOR_INTERVENTIONS*3 lines.
    for line in lines[-_MONITOR_INTERVENTIONS * 3:]:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        verb = str(r.get("command") or "")
        if verb not in _TRADE_VERBS:
            continue
        ts = r.get("ts")
        out.append({
            "ts": _iso(ts),
            "et_date": compute_et_date(ts),
            "verb": verb,
            "symbol": _intervention_symbol(verb, r.get("args") or {}),
            # SECURITY-03: outcome/detail are free-form (built from broker echoes
            # and exception strings) so mask secrets just like the log tail does.
            "outcome": _mask_secrets(str(r.get("outcome", ""))),
            "detail": _mask_secrets(str(r.get("detail", ""))),
        })
    return out[-_MONITOR_INTERVENTIONS:]


def _intervention_symbol(verb: str, args: dict) -> str | None:
    """Best-effort symbol extraction from an InterventionRecord's args."""
    sym = args.get("symbol")
    if sym:
        return str(sym).upper()
    return None


def _turns_summary(path: Path, session: str | None = None) -> dict:
    """Current ET-session turn count + cost + recent turns as structured objects.

    F25: turns are keyed by ET trading date (a session crosses local midnight),
    and ``ts`` is forwarded as a full tz-aware ISO string so the TUI localizes it.
    ``session`` (ET date) defaults to the live/upcoming session; the TUI reads
    turns.jsonl directly for other dates.
    """
    from src.agent.turn_log import compute_et_date, read_turns
    rows = read_turns(path)
    if session is None:
        session = _resolve_session_et_date()
    todays = [r for r in rows if (r.get("et_date") or compute_et_date(r.get("ts"))) == session]
    cost = round(sum(float(r.get("cost_usd") or 0) for r in todays), 4)
    recent = []
    # F22/F25: only the current ET session's turns — stale rows from previous
    # sessions would place markers at unreachable times on the timeline.
    for r in todays[-_MONITOR_TURNS:]:
        recent.append({
            "id": r.get("turn_id", ""),
            "type": r.get("turn_type", "?"),
            "ts": _iso(r.get("ts")),                              # F25: full ISO
            "et_date": r.get("et_date") or compute_et_date(r.get("ts")),
            "cost_usd": round(float(r.get("cost_usd") or 0), 4),
            "num_decisions": r.get("num_decisions", 0),
            "duration_ms": r.get("duration_ms"),
            "summary": r.get("summary", ""),
            "health": r.get("health", "ok"),
        })
    return {"today_count": len(todays), "today_cost_usd": cost, "recent": recent}


def _decisions_tail(path: Path, turns_path: Path | None = None) -> list[dict]:
    """Last N decisions as structured objects with turn_id correlation."""
    from src.agent.steering.jsonl import read_complete_lines
    try:
        lines, _ = read_complete_lines(path, 0)
    except Exception:
        return []

    turn_index = _build_turn_index(turns_path) if turns_path else []

    out: list[dict] = []
    for line in lines[-_MONITOR_DECISIONS:]:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        reason = str(d.get("reason") or "")
        # F22: don't truncate — the TUI overlay constrains display via maxHeight
        turn_id = d.get("turn_id") or _correlate_turn(d.get("ts"), turn_index)
        out.append({
            "turn_id": turn_id,
            "ts": _hhmm(d.get("ts")),
            "symbol": d.get("symbol", "?"),
            "action": d.get("action", "?"),
            "confidence": d.get("confidence"),
            "reason": reason,
            "source": d.get("source", "agent"),
        })
    return out


def _build_turn_index(turns_path: Path | None) -> list[tuple[str, str, str]]:
    """Build [(started_at, ts_end, turn_id), ...] for timestamp correlation."""
    if not turns_path:
        return []
    from src.agent.turn_log import read_turns
    return [
        (r.get("started_at", ""), r.get("ts", ""), r.get("turn_id", ""))
        for r in read_turns(turns_path)
    ]


def _correlate_turn(decision_ts, turn_index: list[tuple[str, str, str]]) -> str | None:
    """Find the turn_id whose [started_at, ts_end] window contains the decision."""
    if not decision_ts or not turn_index:
        return None
    ds = str(decision_ts)
    for started, ended, tid in reversed(turn_index):
        if started and started <= ds:
            return tid
    return None


def _mask_secrets(line: str) -> str:
    line = _SECRET_KV.sub(lambda m: m.group(0).split(m.group(1))[0] + m.group(1) + "=***", line)
    return _SECRET_BLOB.sub("***", line)


def _log_tail(path: Path) -> list[str]:
    """Last N log lines with secrets masked (SECURITY-03)."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [_mask_secrets(ln) for ln in lines[-_MONITOR_LOG:]]

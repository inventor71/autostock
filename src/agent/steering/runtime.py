"""SteeringRuntime: assembles the F4 daemon-side engine and exposes daemon jobs.

Bundles channel + state + bus + coordinator + reconcile worker + command handler,
and provides the periodic jobs the scheduler drives: poll the file-drop channel,
publish the snapshot, drain off-hours trades at the open, and the ET-midnight sweep.
All broker access (commands + snapshot) runs on the single CommandBus worker
(NFR-2). Constructed only when steering is enabled; if absent, the daemon behaves
exactly as before (NFR-8).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from src.agent.steering.bus import CommandBus
from src.agent.steering.jsonl import atomic_write_text
from src.agent.steering.channel import SteeringChannel
from src.agent.steering.commands import CommandHandler
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
        logger.info("Steering runtime started (channel={}, hook installed)", self.steering_dir)

    def stop(self) -> None:
        self.reconcile_worker.stop()
        self.bus.stop()

    # ---- reconcile -------------------------------------------------------- #
    def _reconcile_run_fn(self):
        return self.orchestrator.run_reconcile(self._recent_context())

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
                positions = {s: {"qty": p.qty, "avg_entry_price": p.avg_entry_price,
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
        from src.core.trades import _ET, summarize_today_round_trips

        def _build():
            try:
                fills = self.executor.broker.get_fills(since=since)
                dicts = [
                    {"symbol": f.symbol, "side": f.side, "qty": f.qty,
                     "price": f.price, "ts": f.ts.isoformat()}
                    for f in fills
                ]
                self._round_trip = summarize_today_round_trips(dicts, now_et=datetime.now(_ET))
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
            "started_at": datetime.now().strftime("%H:%M"),
        }

    def clear_current_turn(self) -> None:
        self._current_turn = None

    def publish_monitor(self) -> None:
        """F6 FR-4 / F22: publish structured turns / decisions / agent-log
        summaries to steering/monitor.json. F22 changes: turns.recent and
        decisions are now structured objects (not strings), and current_turn
        shows the in-flight turn. Files only — no broker access."""
        try:
            payload = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "current_turn": self._current_turn,
                "workspace_root": str(self.executor.journal.root),
                "turns": _turns_summary(self.executor.journal.root / "turns.jsonl"),
                "decisions": _decisions_tail(self.executor.journal.root / "decisions.jsonl",
                                             self.executor.journal.root / "turns.jsonl"),
                "log": _log_tail(_REPO_ROOT / "logs" / "autostock.log"),
            }
            atomic_write_text(self.steering_dir / "monitor.json", json.dumps(payload, default=str))
        except Exception as e:
            logger.error("steering monitor publish failed (continuing): {}", e)


# ---- monitor.json helpers (F6 FR-4) ------------------------------------- #
# File-only, defensive, read-only. Build the deep-monitoring view (turn telemetry /
# recent decisions / agent log tail) the operator pulls on demand via steer_read{view}.

_MONITOR_TURNS = 8
_MONITOR_DECISIONS = 10
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


def _turns_summary(path: Path) -> dict:
    """Today's turn count + total cost + the last few turns as structured objects."""
    from src.agent.turn_log import read_turns
    rows = read_turns(path)
    today = datetime.now().date().isoformat()
    todays = [r for r in rows if str(r.get("date", "")) == today]
    cost = round(sum(float(r.get("cost_usd") or 0) for r in todays), 4)
    recent = []
    # F22: only today's turns — stale rows from previous runs would place
    # markers at unreachable times on today's timeline.
    for r in todays[-_MONITOR_TURNS:]:
        recent.append({
            "id": r.get("turn_id", ""),
            "type": r.get("turn_type", "?"),
            "ts": _hhmm(r.get("ts")),
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

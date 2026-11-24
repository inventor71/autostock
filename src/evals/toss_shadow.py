"""Toss shadow experiment: init, bounded observe/agent run, and offline report.

python -m src.evals.toss_shadow --dir research-comparisons/toss-shadow/trial init
python -m src.evals.toss_shadow --dir research-comparisons/toss-shadow/trial run --agent
python -m src.evals.toss_shadow --dir research-comparisons/toss-shadow/trial report
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from config.config import AgentConfig, RiskConfig, get_settings
from src.agent.executor import DecisionExecutor, ExecutionOutcome
from src.agent.orchestrator import AgentTradingLoop
from src.core.exceptions import BrokerError
from src.execution.brokers.factory import create_broker
from src.execution.brokers.toss import storage
from src.execution.brokers.toss.broker import _time
from src.execution.brokers.toss.costs import ET


class ShadowExecutor(DecisionExecutor):
    """Decision identity survives a crash between ledger commit and journal cursor."""
    def execute_decision(self, decision, *, decision_index=-1):
        key = "decision-" + hashlib.sha256(
            (str(decision_index) + "\0" + decision.model_dump_json()).encode()
        ).hexdigest()[:32]
        existing = self.broker.get_order_status(key)
        if existing is not None:
            self._clear_retry(key)
            return ExecutionOutcome(decision, "executed", "Recovered durable shadow order", order_id=key)
        # Failed decisions remain pending, but polling must not hammer the same
        # invalid order. Identity includes the content: a revised intent is fresh.
        state = self.broker.read()
        retry = state.get("execution_retries", {}).get(key)
        expired = decision.valid_until is not None and decision.valid_until < self._clock(decision.valid_until)
        if retry and not expired and self.broker.clock() < _time(retry["next_retry_at"]):
            return ExecutionOutcome(decision, "no_order", f"Retry deferred until {retry['next_retry_at']}")
        quality = state.get("quote_quality")
        if decision.action == "BUY" and not expired and quality and not quality["valuation_usable"]:
            return ExecutionOutcome(decision, "no_order", "Portfolio valuation is not current enough for new exposure")
        self.broker.decision_key = key
        try:
            outcome = super().execute_decision(decision, decision_index=decision_index)
        except Exception as exc:  # Persist backoff, then retain the executor's error audit.
            self._record_retry(key, decision, decision_index, str(exc))
            raise
        finally:
            self.broker.decision_key = None
        if outcome.status == "error":
            self._record_retry(key, decision, decision_index, outcome.detail)
        else:
            self._clear_retry(key)
        return outcome

    def _record_retry(self, key, decision, index, detail):
        with self.broker.transaction() as state:
            retries = state.setdefault("execution_retries", {})
            previous = retries.get(key, {})
            attempts = previous.get("attempts", 0) + 1
            delay = min(300, 30 * 2 ** min(attempts - 1, 4))
            retries[key] = {"decision_index": index, "symbol": decision.symbol, "action": decision.action,
                            "attempts": attempts, "last_error": detail,
                            "next_retry_at": (self.broker.clock() + timedelta(seconds=delay)).isoformat()}

    def _clear_retry(self, key):
        if key in self.broker.read().get("execution_retries", {}):
            with self.broker.transaction() as state:
                state["execution_retries"].pop(key, None)

    def execute_pending(self):
        outcomes = super().execute_pending()
        cursor, terminal = self._load_cursor()
        if self.broker.read().get("execution_retries"):
            with self.broker.transaction() as state:
                state["execution_retries"] = {k: r for k, r in state["execution_retries"].items()
                                              if r["decision_index"] >= cursor and r["decision_index"] not in terminal}
        return outcomes


class ShadowTradingLoop(AgentTradingLoop):
    def __init__(self, *args, shadow_broker, **kwargs):
        super().__init__(*args, **kwargs)
        self.shadow_broker = shadow_broker

    def _assemble_turn(self, core, *, lessons=""):
        state = self.shadow_broker.read()
        profile = self.shadow_broker.get_cost_profile()
        quality = state.get("quote_quality") or {}
        quality_summary = {k: quality.get(k) for k in (
            "as_of", "status", "fresh_value_pct", "indicative_symbols", "unavailable_symbols")}
        context = (
            "This is a separate Toss USD shadow account. Use the account tool for this virtual book. "
            "Judge opportunities after costs; prefer no trade when the edge is uncertain. "
            f"Commission is {float(profile['commission']['rate']) * 10000:g} bps per side; "
            "sells also incur estimated SEC fees. Bid/ask spread and adverse slippage apply. "
            f"Execution assumptions: {json.dumps(state['execution'])}. "
            "Stops/OCO are local simulations, not available live Toss brackets. "
            "Annual capital-gains tax is handled separately. Keep the decision rationale concise."
            " For a partial exit followed by protection, write SELL then HOLD with stop/target; "
            "protection waits for the exit to finish and uses the actual remaining quantity. "
            "Check the account's open orders and actual fills: a recorded decision is not a fill. "
            "Use current quotes for stop/target levels; a target already crossed is not a protective exit. "
            f"Latest portfolio quote quality: {json.dumps(quality_summary)}."
        )
        return context + "\n\n" + super()._assemble_turn(core, lessons=lessons)


def configure_environment(root: Path):
    """The daemon and every agent market-data subprocess must share this account."""
    overrides = {
        "AUTOSTOCK_BROKER_PROVIDER": "toss_shadow", "AUTOSTOCK_BROKER_PAPER": "true",
        "AUTOSTOCK_DATA_PROVIDER": "toss", "AUTOSTOCK_APP_MODE": "paper",
        "AUTOSTOCK_TOSS_READ_ONLY": "true", "AUTOSTOCK_SHADOW_DIR": str(root),
        "AGENT_JOURNAL_ROOT": str(root / "workspace"),
    }
    os.environ.update(overrides)
    # Fixture/replay switches must never silently substitute prices for a live observation experiment.
    for name in ("AUTOSTOCK_TOOLS_FIXTURE_DIR", "AUTOSTOCK_TOOLS_RECORD_DIR"):
        os.environ.pop(name, None)
    get_settings.cache_clear()
    return get_settings()


def build_agent(settings, broker):
    from main import _build_risk_manager
    from src.agent.session import AgentSession
    from src.agent.steering.security import write_agent_hook_settings
    from src.data.providers.toss_provider import TossDataProvider

    frozen = broker.read()
    settings = settings.model_copy(deep=True)
    settings.agent = AgentConfig.model_validate(frozen["agent_config"])
    settings.risk = RiskConfig.model_validate(frozen["risk_config"])
    settings.risk.shorting_enabled = False
    cfg = settings.agent
    workspace = broker.root / "workspace"
    storage.private_dir(workspace)
    if cfg.provider == "openai":
        from src.agent.openai_session import OpenAIAgentSession
        session = OpenAIAgentSession(workspace, api_key=settings.openai_api_key,
                                    model=cfg.model, effort=cfg.effort, timeout=cfg.turn_timeout,
                                    max_output_tokens=cfg.max_output_tokens)
    else:
        session = AgentSession(workspace, model=cfg.model, effort=cfg.effort, timeout=cfg.turn_timeout)
    session.journal.init()
    recover_interrupted_turns(broker, session.journal)
    write_agent_hook_settings(workspace)  # File tools cannot edit the sibling account ledger.
    provider = TossDataProvider(broker.client)
    loop = ShadowTradingLoop(
        session, shadow_broker=broker, universe=frozen["universe"],
        portfolio_provider=broker.get_portfolio_state, price_provider=provider.get_latest_price,
        research_model=cfg.research_model, research_effort=cfg.research_effort,
        research_timeout=cfg.research_timeout, shorting_enabled=False,
        aggressiveness=cfg.aggressiveness, multi_agent_enabled=False,
        reflection_enabled=False,  # Freeze policy across the observation window.
    )
    executor = ShadowExecutor(
        broker, _build_risk_manager(settings, use_bracket_orders=True, apply_aggressiveness=True),
        provider, session.journal, universe=frozen["universe"],
    )
    return loop, executor


def claim_turn(broker):
    """Persist the attempt BEFORE model invocation; restarts/errors consume budget."""
    now = broker.clock()
    with broker.transaction() as state:
        if now >= _time(state["end_at"]):
            return None
        day = now.astimezone(ET).date().isoformat()
        today = [t for t in state["turns"] if t["day"] == day]
        cfg = state["runner"]
        if len(today) >= cfg["max_turns_per_day"]:
            return None
        if today and now < _time(today[-1]["started_at"]) + timedelta(minutes=cfg["interval_minutes"]):
            return None
        turn = {"id": len(state["turns"]), "day": day, "started_at": now.isoformat(),
                "kind": "research" if not today else "intraday", "status": "claimed"}
        state["turns"].append(turn)
        return turn


def recover_interrupted_turns(broker, journal):
    """A crashed model's partial journal edits must not become later trades."""
    from src.core.jsonl import atomic_write_text

    with broker.transaction() as state:
        for turn in state["turns"]:
            if turn["status"] not in {"claimed", "started", "executing"}:
                continue
            if turn["status"] == "started":
                backup = storage.read_json(broker.root / "turn-backup.json")
                if backup.get("turn_id") != turn["id"]:
                    raise BrokerError("Interrupted shadow model turn lacks its decision backup")
                atomic_write_text(journal.decisions_file, backup["decisions"])
            # executing means the model completed; keep its decisions and let
            # the durable order identity protect against a cursor-crash duplicate.
            turn.update(status="error", error_type="InterruptedTurn",
                        finished_at=broker.clock().isoformat())


def do_turn(broker, loop, executor, turn, stop):
    status, error_type = "complete", None
    journal = getattr(loop, "journal", None)
    original = journal.decisions_file.read_text() if journal and journal.decisions_file.exists() else ""
    model_complete = False
    try:
        if journal:
            storage.write_json(broker.root / "turn-backup.json", {"turn_id": turn["id"], "decisions": original})
        with broker.transaction() as state:
            state["turns"][turn["id"]]["status"] = "started"
        if turn["kind"] == "research":
            result = loop.run_morning_research()
        else:
            result = loop.run_intraday()
        if getattr(result, "raw", {}).get("is_error"):
            raise BrokerError("Agent turn did not complete successfully")
        model_complete = True
        with broker.transaction() as state:
            state["turns"][turn["id"]]["status"] = "executing"
        if stop.is_set() or broker.clock() >= _time(broker.read()["end_at"]):
            status = "stopped"
            if journal:
                from src.core.jsonl import atomic_write_text
                atomic_write_text(journal.decisions_file, original)
        else:
            executor.execute_pending()
    except Exception as exc:  # noqa: BLE001 — record provider/executor failures without losing the run
        status, error_type = "error", type(exc).__name__
        if journal and not model_complete:
            from src.core.jsonl import atomic_write_text
            atomic_write_text(journal.decisions_file, original)
    with broker.transaction() as state:
        state["turns"][turn["id"]].update(status=status, error_type=error_type,
                                         finished_at=broker.clock().isoformat())


def run(broker, settings, *, agent=False, once=False, seconds=None, poll_seconds=5):
    broker.read()  # Missing/corrupt ledgers fail before any worker or signal handler starts.
    if poll_seconds < 1 or (seconds is not None and seconds <= 0):
        raise BrokerError("Positive runtime and poll interval >=1s required")
    if once and agent:
        raise BrokerError("--once observes only; use run --agent for the bounded experiment")
    stop = threading.Event()
    previous_handlers = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[sig] = signal.signal(sig, lambda *_: stop.set())
    future = None
    started = time.monotonic()
    # Nonblocking run lock: a duplicate launch must fail, not wait and later start
    # a second experiment when the first finally exits.
    import fcntl
    fd = os.open(broker.root / "runner.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        storage._check_file(fd)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BrokerError("This shadow run already has an active runner") from None
        with broker.transaction() as state:
            revisions = state.setdefault("runtime_revisions", [])
            if not revisions or revisions[-1]["implementation"] != "F104":
                revisions.append({"implementation": "F104", "started_at": broker.clock().isoformat(),
                                  "note": "Floor Toss market-sell quantities to six decimals; durable execution retry backoff"})
            state.pop("runner_stopped_at", None)
        if agent:
            loop, executor = build_agent(settings, broker)
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="shadow-agent") as pool:
            try:
                while not stop.is_set():
                    now = broker.clock()
                    if now >= _time(broker.read()["end_at"]) or (seconds and time.monotonic() - started >= seconds):
                        break
                    try:
                        report = broker.poll()
                        within_deadline = (not stop.is_set() and broker.clock() < _time(broker.read()["end_at"])
                                           and not (seconds and time.monotonic() - started >= seconds))
                        if agent and within_deadline and (future is None or future.done()) and report["health"].get("market_open"):
                            # Finish deferred protection after an asynchronous fill without
                            # waiting for another model turn. Never read a journal mid-turn.
                            executor.execute_pending()
                            ready = report["health"].get("agent_ready", not report["health"].get("cost_error"))
                            if ready:
                                turn = claim_turn(broker)
                                if turn is not None:
                                    future = pool.submit(do_turn, broker, loop, executor, turn, stop)
                    except Exception as exc:  # noqa: BLE001 — keep observing after transient outages
                        with broker.transaction() as state:
                            state["health"] = {"status": "error", "as_of": broker.clock().isoformat(),
                                               "error_type": type(exc).__name__}
                            state["metrics"]["blocked_polls"] += 1
                            state["metrics"]["polls"] += 1
                    if once:
                        break
                    stop.wait(poll_seconds)
            finally:
                # No decisions from an in-flight final turn are executed after stop.
                # Its existing provider timeout bounds shutdown; quote polling stops here.
                stop.set()
        with broker.transaction() as state:
            state["runner_stopped_at"] = broker.clock().isoformat()
            if broker.clock() >= _time(state["end_at"]):
                from src.execution.brokers.toss.shadow import OPEN
                state["health"]["status"] = "ended"
                state["health"]["agent_ready"] = False
                for row in state["orders"].values():
                    if row["status"] in OPEN:
                        row["status"] = "expired"
    finally:
        os.close(fd)
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
    return broker.report()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, type=Path, help="Private, independent experiment directory")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Read Toss once and seed a new virtual account")
    init.add_argument("--days", type=int, default=7, help="Calendar days; persisted across restarts")
    init.add_argument("--symbols", help="Comma-separated pool, unioned with existing US holdings")
    init.add_argument("--interval-minutes", type=int, default=60)
    init.add_argument("--max-turns-per-day", type=int, default=8)
    init.add_argument("--latency-seconds", type=float, default=1)
    init.add_argument("--slippage-bps", type=float, default=2)
    init.add_argument("--participation", type=float, default=0.1)
    start = sub.add_parser("run", help="Observe continuously; --agent additionally invokes the configured model")
    start.add_argument("--agent", action="store_true")
    start.add_argument("--once", action="store_true")
    start.add_argument("--seconds", type=float)
    start.add_argument("--poll-seconds", type=float, default=5)
    sub.add_parser("report", help="Read results without contacting any API")
    args = parser.parse_args(argv)
    os.umask(0o077)
    root = args.dir.expanduser().absolute()
    settings = configure_environment(root)
    broker = create_broker(settings)
    try:
        if args.command == "init":
            if not 1 <= args.interval_minutes <= 1440 or not 1 <= args.max_turns_per_day <= 100:
                raise BrokerError("Invalid model cadence/call budget")
            from src.universe.factory import resolve_universe
            symbols = ([s.strip().upper() for s in args.symbols.split(",") if s.strip()]
                       if args.symbols else resolve_universe(settings))
            broker.initialize(days=args.days, symbols=symbols, latency_seconds=args.latency_seconds,
                              slippage_bps=args.slippage_bps, participation=args.participation,
                              runtime={"agent_config": settings.agent.model_dump(mode="json"),
                                       "risk_config": {**settings.risk.model_dump(mode="json"),
                                                       "shorting_enabled": False},
                                       "runner": {"interval_minutes": args.interval_minutes,
                                                  "max_turns_per_day": args.max_turns_per_day}})
            result = broker.report()
        elif args.command == "run":
            result = run(broker, settings, agent=args.agent, once=args.once, seconds=args.seconds,
                         poll_seconds=args.poll_seconds)
        else:
            result = broker.report()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (BrokerError, ValueError) as exc:
        parser.exit(1, f"Toss shadow: {exc}\n")
    finally:
        broker.close()


if __name__ == "__main__":
    raise SystemExit(main())

"""Unit A steering-core -- Step 9/10: SteeringRuntime wiring + AgentTradingMode funnel.

Exercises the live-daemon wiring end-to-end WITHOUT a real `claude` (the orchestrator
turns are stubs): a dropped command flows poll -> bus worker -> handler -> state/broker;
snapshot/sweep work; and the paused gate routes through the funnel (exits only)."""

from __future__ import annotations

import json
import time

import pandas as pd

from src.agent.executor import DecisionExecutor
from src.agent.journal import Journal
from src.agent.steering.records import SteeringCommand, SteeringEvent
from src.agent.steering.runtime import SteeringRuntime
from src.core.models import Order
from src.core.types import OrderSide
from src.execution.brokers.simulated_broker import SimulatedBroker
from src.risk.manager import RiskManager
from src.trading.modes.agent import AgentTradingMode


class _StubOrchestrator:
    def __init__(self):
        self.calls = []
        self.last_new_decisions = []
        self.last_kept = []

    def run_morning_research(self):
        self.calls.append("research")
        # mimic a turn that produced decisions (read by the F38 completion event)
        self.last_new_decisions = [object(), object()]
        self.last_kept = [object()]
    def run_intraday(self, quotes=None): self.calls.append("intraday")
    def run_eod_review(self, outcomes=None): self.calls.append("eod")
    def run_reconcile(self, context=""): self.calls.append("reconcile"); return "ok"


class _Provider:
    def get_latest_price(self, symbol): return 100.0
    def get_bars(self, symbol, timeframe=None, start=None, end=None, limit=100):
        idx = pd.date_range("2024-01-01", periods=2, freq="D")
        return pd.DataFrame({"open": [500, 500], "high": [500, 500], "low": [500, 500],
                             "close": [500, 500], "volume": [1, 1]}, index=idx)


def _runtime(tmp_path):
    broker = SimulatedBroker(initial_capital=100_000.0)
    broker.set_current_price("AAPL", 100.0)
    rm = RiskManager(use_bracket_orders=True)
    ex = DecisionExecutor(broker, rm, _Provider(), journal=Journal(root=tmp_path / "ws"),
                          universe=["AAPL", "MSFT"])
    ex._atr = lambda s: 2.0
    orch = _StubOrchestrator()
    rt = SteeringRuntime(ex, orch, steering_dir=tmp_path / "steering", token="tok")
    return rt, broker, orch


def _drop(rt, **kw):
    cmd = SteeringCommand(token="tok", confirmed=True, **kw)
    with rt.channel.commands_file.open("a", encoding="utf-8") as fh:
        fh.write(cmd.model_dump_json() + "\n")
    return cmd


def _wait(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def _events(rt):
    p = rt.channel.events_file
    if not p.exists():
        return []
    return [SteeringEvent.model_validate_json(ln) for ln in p.read_text().splitlines() if ln.strip()]


def test_research_triggers_then_reports_completion(tmp_path):
    # F38: /research starts a background turn (skip-if-busy), and when it finishes a
    # completion event correlated to the triggering command is published — so the
    # operator gets a result report without polling.
    rt, _, orch = _runtime(tmp_path)
    rt.start()
    try:
        cmd = _drop(rt, verb="research")
        rt.poll_commands()
        assert _wait(lambda: any(e.payload.get("outcome") == "completed" for e in _events(rt)))
        evs = _events(rt)
        outcomes = [e.payload.get("outcome") for e in evs]
        assert "triggered" in outcomes and "completed" in outcomes
        comp = next(e for e in evs if e.payload.get("outcome") == "completed")
        assert comp.corr_id == cmd.id                  # correlated to the trigger
        assert "2 decision" in comp.payload["detail"]  # decision count reported
        assert "1 in-universe" in comp.payload["detail"]
        assert orch.calls.count("research") == 1       # the turn actually ran once
    finally:
        rt.stop()


def test_research_reports_failure_when_turn_raises(tmp_path):
    rt, _, orch = _runtime(tmp_path)
    orch.run_morning_research = lambda: (_ for _ in ()).throw(RuntimeError("llm down"))
    rt.start()
    try:
        cmd = _drop(rt, verb="research")
        rt.poll_commands()
        assert _wait(lambda: any(e.payload.get("outcome") == "failed" for e in _events(rt)))
        comp = next(e for e in _events(rt) if e.payload.get("outcome") == "failed")
        assert comp.corr_id == cmd.id
        assert "llm down" in comp.payload["detail"]
    finally:
        rt.stop()


def test_dropped_command_flows_poll_bus_handler(tmp_path):
    rt, broker, _ = _runtime(tmp_path)
    rt.start()
    try:
        _drop(rt, verb="pause")
        rt.poll_commands()
        assert _wait(lambda: rt.state.run_state().paused)
        # a buy command lands a position via the worker
        _drop(rt, verb="buy", args={"symbol": "AAPL", "size": 1000.0, "unit": "$"})
        rt.poll_commands()
        assert _wait(lambda: broker.get_position("AAPL") is not None)
        assert rt.state.lock_status("AAPL") == "locked"
    finally:
        rt.stop()


def test_bad_token_command_rejected(tmp_path):
    rt, broker, _ = _runtime(tmp_path)
    rt.start()
    try:
        with rt.channel.commands_file.open("a", encoding="utf-8") as fh:
            fh.write(SteeringCommand(verb="kill", confirmed=True, token="WRONG").model_dump_json() + "\n")
        rt.poll_commands()
        time.sleep(0.2)
        assert not rt.state.run_state().paused  # kill never executed
        assert "WRONG" not in rt.channel.events_file.read_text()  # token not logged
    finally:
        rt.stop()


def test_publish_snapshot_and_sweep(tmp_path):
    rt, broker, _ = _runtime(tmp_path)
    rt.start()
    try:
        broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=5.0))
        rt.publish_snapshot()
        assert _wait(lambda: rt.channel.snapshot_file.exists())
        snap = json.loads(rt.channel.snapshot_file.read_text())
        assert "AAPL" in snap["positions"] and "run_state" in snap and "published_at" in snap
        # F43: the snapshot carries the daemon's code version (git HEAD or "" off-git) so the
        # launcher can detect a daemon left running stale code and auto-restart it (AC-1).
        assert "code_version" in snap and isinstance(snap["code_version"], str)
        # sweep clears day-scoped state without error
        rt.state.lock_symbol("AAPL")
        rt.daily_sweep()
    finally:
        rt.stop()


def test_reconcile_run_fn_invokes_orchestrator(tmp_path):
    rt, _, orch = _runtime(tmp_path)
    assert rt._reconcile_run_fn() == "ok"
    assert "reconcile" in orch.calls


def test_agent_mode_paused_runs_exits_not_turns(tmp_path):
    rt, broker, orch = _runtime(tmp_path)
    rt.start()
    try:
        mode = AgentTradingMode(orch, rt.executor, steering=rt)
        rt.state.set_paused(True)
        mode._intraday()  # paused -> exits only, no LLM turn
        time.sleep(0.1)
        assert "intraday" not in orch.calls
        # unpause -> the scheduled turn runs (via coordinator) through the funnel
        rt.state.set_paused(False)
        mode._intraday()
        assert _wait(lambda: "intraday" in orch.calls)
    finally:
        rt.stop()


def test_agent_question_pushed_and_answered(tmp_path):
    rt, broker, _ = _runtime(tmp_path)
    rt.start()
    try:
        from src.agent.steering.records import AgentQuestion, SteeringEvent
        q = AgentQuestion(symbol="AAPL", text="re-enter after stop?")
        qfile = rt.executor.journal.root / "agent_questions.jsonl"
        rt.executor.journal.root.mkdir(parents=True, exist_ok=True)
        qfile.write_text(q.model_dump_json() + "\n", encoding="utf-8")
        rt.poll_agent_questions()
        ev = SteeringEvent.model_validate_json(rt.channel.events_file.read_text().splitlines()[-1])
        assert ev.kind == "agent_question" and ev.payload["id"] == q.id
        rt.poll_agent_questions()  # idempotent: not pushed twice
        assert len(rt.channel.events_file.read_text().splitlines()) == 1
        # operator answers -> persisted to a separate file (append-only)
        _drop(rt, verb="answer", args={"id": q.id, "text": "no, stand down"})
        rt.poll_commands()
        ans = rt.executor.journal.root / "agent_answers.jsonl"
        assert _wait(lambda: ans.exists() and q.id in ans.read_text())
    finally:
        rt.stop()


def test_offhours_drain_enqueues(tmp_path, monkeypatch):
    rt, broker, _ = _runtime(tmp_path)
    rt.start()
    try:
        monkeypatch.setattr(broker, "is_market_open", lambda: False)
        _drop(rt, verb="buy", args={"symbol": "AAPL", "size": 1000.0, "unit": "$"})
        rt.poll_commands()
        time.sleep(0.2)
        assert broker.get_position("AAPL") is None  # deferred off-hours
        # at the open: drain re-enqueues and it executes
        monkeypatch.setattr(broker, "is_market_open", lambda: True)
        rt.drain_offhours()
        assert _wait(lambda: broker.get_position("AAPL") is not None)
    finally:
        rt.stop()

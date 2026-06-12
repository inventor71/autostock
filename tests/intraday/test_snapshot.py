"""Step 3 — snapshot fills payload + in-proc last_snapshot (critic#3/#4)."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from src.agent.executor import DecisionExecutor
from src.agent.intraday.records import FillEvent
from src.agent.journal import Journal
from src.agent.steering.runtime import SteeringRuntime
from src.risk.manager import RiskManager
from src.execution.brokers.simulated_broker import SimulatedBroker


class _Orch:
    def run_reconcile(self, context=""):
        return "ok"


class _Provider:
    def get_latest_price(self, symbol):
        return 100.0


def _runtime(tmp_path):
    broker = SimulatedBroker(initial_capital=100_000.0)
    rm = RiskManager(use_bracket_orders=True)
    ex = DecisionExecutor(broker, rm, _Provider(), journal=Journal(root=tmp_path / "ws"),
                          universe=["AAPL"])
    rt = SteeringRuntime(ex, _Orch(), steering_dir=tmp_path / "steering", token="tok")
    return rt, broker


def _wait(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def _fake_fills(events):
    """A get_fills that honors the ``since`` (transaction_time) cursor inclusively
    at the boundary so dedup-by-id is exercised."""
    def _get(since=None):
        if since is None:
            return list(events)
        cur = datetime.fromisoformat(since)
        return [e for e in events if e.ts >= cur]
    return _get


def test_publish_populates_last_snapshot_and_new_fills_once(tmp_path):
    rt, broker = _runtime(tmp_path)
    rt.start()
    try:
        f = FillEvent(fill_id="a1", symbol="AAPL", qty=10, price=100.0, side="buy",
                      ts=datetime(2026, 5, 30, 14, 31, tzinfo=timezone.utc))
        broker.get_fills = _fake_fills([f])
        rt._fills_cursor = "2020-01-01T00:00:00+00:00"  # so the fill counts as new
        rt._seen_fill_ids = set()

        rt.publish_snapshot()
        assert _wait(lambda: rt.last_snapshot is not None)
        snap = rt.last_snapshot
        assert "positions" in snap and "open_orders" in snap and "run_state" in snap
        assert [x["fill_id"] for x in snap["fills"]] == ["a1"]

        # second publish: same fill is returned by the cursor boundary but must be
        # deduped -> no longer "new".
        rt.last_snapshot = None
        rt.publish_snapshot()
        assert _wait(lambda: rt.last_snapshot is not None)
        assert rt.last_snapshot["fills"] == []
    finally:
        rt.stop()


def test_fills_cursor_persisted(tmp_path):
    rt, broker = _runtime(tmp_path)
    rt.start()
    try:
        f = FillEvent(fill_id="a1", symbol="AAPL", qty=1, price=100.0, side="buy",
                      ts=datetime(2026, 5, 30, 14, 31, tzinfo=timezone.utc))
        broker.get_fills = _fake_fills([f])
        rt._fills_cursor = "2020-01-01T00:00:00+00:00"
        rt._seen_fill_ids = set()
        rt.publish_snapshot()
        assert _wait(lambda: rt._fills_cursor_file.exists())
        assert rt._fills_cursor_file.read_text().startswith("2026-05-30T14:31")
    finally:
        rt.stop()


def test_first_run_cursor_starts_now_no_history_flood(tmp_path):
    # No persisted cursor -> cursor defaults to "now", so a historical fill is NOT
    # re-surfaced as new at startup.
    rt, broker = _runtime(tmp_path)
    rt.start()
    try:
        old = FillEvent(fill_id="old", symbol="AAPL", qty=1, price=100.0, side="buy",
                        ts=datetime(2020, 1, 1, tzinfo=timezone.utc))
        broker.get_fills = _fake_fills([old])
        rt.publish_snapshot()
        assert _wait(lambda: rt.last_snapshot is not None)
        assert rt.last_snapshot["fills"] == []  # old fill is before the "now" cursor
    finally:
        rt.stop()

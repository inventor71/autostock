"""F6 console-sidebar-upgrade — daemon-side tests (integrated onto main/F3).

Covers today's round-trip summary (UTC→ET boundary, win_rate bounds), the account
block reuse, and the snapshot account/round_trip + monitor.json publishing. The
round-trip refresh consumes F3's `get_fills` (FillEvent) stream, converted to the
match_round_trips dict shape inside SteeringRuntime.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from src.agent.executor import DecisionExecutor
from src.agent.intraday.records import FillEvent
from src.agent.journal import Journal
from src.agent.steering.runtime import SteeringRuntime
from src.core.trades import summarize_today_round_trips
from src.execution.brokers.simulated import SimulatedBroker
from src.risk.manager import RiskManager

_ET = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")


# --------------------------------------------------------------------------- #
# summarize_today_round_trips
# --------------------------------------------------------------------------- #
def test_round_trip_today_only():
    now_et = datetime(2026, 5, 29, 12, 0, tzinfo=_ET)
    fills = [
        {"symbol": "AAPL", "side": "buy", "qty": 10, "price": 100, "ts": "2026-05-28T14:00:00+00:00"},
        {"symbol": "AAPL", "side": "sell", "qty": 10, "price": 110, "ts": "2026-05-29T15:00:00+00:00"},
        {"symbol": "MSFT", "side": "buy", "qty": 5, "price": 200, "ts": "2026-05-28T14:00:00+00:00"},
        {"symbol": "MSFT", "side": "sell", "qty": 5, "price": 190, "ts": "2026-05-28T18:00:00+00:00"},
    ]
    s = summarize_today_round_trips(fills, now_et=now_et)
    assert s["closed_count"] == 1
    assert s["win_rate"] == 1.0
    assert s["realized_pnl"] == 100.0


def test_round_trip_empty():
    s = summarize_today_round_trips([], now_et=datetime(2026, 5, 29, 12, 0, tzinfo=_ET))
    assert s["closed_count"] == 0
    assert s["win_rate"] is None
    assert s["realized_pnl"] == 0.0


def test_round_trip_utc_et_boundary():
    """A sell at UTC 02:00 on 05-29 is 22:00 ET on 05-28 -> belongs to ET-28, not 29."""
    fills = [
        {"symbol": "AAPL", "side": "buy", "qty": 1, "price": 100, "ts": "2026-05-28T18:00:00+00:00"},
        {"symbol": "AAPL", "side": "sell", "qty": 1, "price": 105, "ts": "2026-05-29T02:00:00+00:00"},
    ]
    assert summarize_today_round_trips(fills, now_et=datetime(2026, 5, 29, 12, 0, tzinfo=_ET))["closed_count"] == 0
    assert summarize_today_round_trips(fills, now_et=datetime(2026, 5, 28, 23, 0, tzinfo=_ET))["closed_count"] == 1


_fill = st.fixed_dictionaries({
    "symbol": st.sampled_from(["AAPL", "MSFT"]),
    "side": st.sampled_from(["buy", "sell"]),
    "qty": st.integers(min_value=1, max_value=100),
    "price": st.integers(min_value=1, max_value=1000),
    "ts": st.sampled_from([
        "2026-05-29T15:00:00+00:00", "2026-05-28T15:00:00+00:00", "2026-05-29T18:30:00+00:00",
    ]),
})


@settings(max_examples=150)
@given(fills=st.lists(_fill, max_size=12))
def test_round_trip_invariants(fills):
    s = summarize_today_round_trips(fills, now_et=datetime(2026, 5, 29, 12, 0, tzinfo=_ET))
    assert s["closed_count"] >= 0
    assert s["win_rate"] is None or 0.0 <= s["win_rate"] <= 1.0
    assert isinstance(s["realized_pnl"], float)


# --------------------------------------------------------------------------- #
# broker get_fills (F3 port) + account block
# --------------------------------------------------------------------------- #
def test_get_fills_noop_default():
    assert SimulatedBroker(initial_capital=100_000.0).get_fills() == []


def test_account_block_reuses_equity_log():
    ps = SimulatedBroker(initial_capital=100_000.0).get_portfolio_state()
    acc = SteeringRuntime._account_block(ps)
    assert set(acc) == {"equity", "cash", "open_pnl", "position_count"}
    assert acc["cash"] == 100_000.0
    assert acc["position_count"] == 0


# --------------------------------------------------------------------------- #
# SteeringRuntime publishing
# --------------------------------------------------------------------------- #
class _StubOrchestrator:
    def run_reconcile(self, context=""): return "ok"


class _Provider:
    def get_latest_price(self, symbol): return 100.0
    def get_bars(self, symbol, timeframe=None, start=None, end=None, limit=100):
        idx = pd.date_range("2024-01-01", periods=2, freq="D")
        return pd.DataFrame({"open": [1, 1], "high": [1, 1], "low": [1, 1],
                             "close": [1, 1], "volume": [1, 1]}, index=idx)


def _runtime(tmp_path):
    broker = SimulatedBroker(initial_capital=100_000.0)
    broker.set_current_price("AAPL", 100.0)
    ex = DecisionExecutor(broker, RiskManager(use_bracket_orders=True), _Provider(),
                          journal=Journal(root=tmp_path / "ws"), universe=["AAPL"])
    ex._atr = lambda s: 2.0
    rt = SteeringRuntime(ex, _StubOrchestrator(), steering_dir=tmp_path / "steering", token="tok")
    return rt, broker


def _wait(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_snapshot_includes_account_and_round_trip(tmp_path):
    rt, _ = _runtime(tmp_path)
    rt.start()
    try:
        rt._round_trip = {"closed_count": 2, "win_rate": 0.5, "realized_pnl": 12.0, "as_of": "x"}
        rt.publish_snapshot()
        assert _wait(lambda: rt.channel.snapshot_file.exists())
        snap = json.loads(rt.channel.snapshot_file.read_text())
        assert set(snap["account"]) == {"equity", "cash", "open_pnl", "position_count"}
        assert snap["round_trip"]["closed_count"] == 2
    finally:
        rt.stop()


def test_refresh_round_trip_reads_broker_fills(tmp_path):
    rt, broker = _runtime(tmp_path)
    today = datetime.now(_ET).date()
    t = datetime(today.year, today.month, today.day, 15, 0, tzinfo=_UTC)
    # F3 get_fills returns FillEvent objects; SteeringRuntime converts them for matching.
    broker.get_fills = lambda since=None: [
        FillEvent(fill_id="1", symbol="AAPL", qty=1, price=100, side="buy", ts=t),
        FillEvent(fill_id="2", symbol="AAPL", qty=1, price=90, side="sell",
                  ts=t.replace(hour=16)),
    ]
    rt.start()
    try:
        rt.refresh_round_trip()
        assert _wait(lambda: rt._round_trip.get("closed_count") == 1)
        assert rt._round_trip["win_rate"] == 0.0  # a loss
    finally:
        rt.stop()


def test_publish_monitor_writes_file_and_masks_secrets(tmp_path):
    rt, _ = _runtime(tmp_path)
    root = rt.executor.journal.root
    root.mkdir(parents=True, exist_ok=True)
    (root / "turns.jsonl").write_text(json.dumps({
        "ts": "2026-05-29T10:00:00", "date": datetime.now().date().isoformat(),
        "turn_type": "intraday", "cost_usd": 0.12, "num_decisions": 1}) + "\n")
    (root / "decisions.jsonl").write_text(json.dumps({
        "ts": "2026-05-29T10:00:00", "symbol": "AAPL", "action": "BUY",
        "confidence": 0.7, "reason": "breakout"}) + "\n")
    rt.publish_monitor()
    mon = json.loads((rt.steering_dir / "monitor.json").read_text())
    assert mon["turns"]["today_count"] == 1
    assert any("AAPL" in d for d in mon["decisions"])
    assert "turns" in mon and "log" in mon


def test_publish_monitor_log_masks_token():
    from src.agent.steering.runtime import _mask_secrets
    masked = _mask_secrets("STEERING_OPERATOR_TOKEN=abcdef0123456789abcdef0123")
    assert "abcdef0123456789abcdef0123" not in masked

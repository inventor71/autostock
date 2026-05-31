"""F8 console-sidebar-status-rich — daemon-side unit tests.

Covers the snapshot enrichment (positions current_price/market_value/unrealized_pnl,
open_orders side/order_type/current_price, account invested, recent_fills) and the
two slow-cadence worker jobs (PriceBook for order-only symbols + recent_fills),
plus the PriceBook TTL. Console TS derivations (role/pnl%/Δ/color) are bun-tested.

Reuses the same real-executor harness as test_steering_runtime / test_sidebar_upgrade
(SimulatedBroker + DecisionExecutor), so CommandHandler wiring is satisfied.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta

import pandas as pd

from src.agent.executor import DecisionExecutor
from src.agent.intraday.records import FillEvent
from src.agent.journal import Journal
from src.agent.steering.runtime import SteeringRuntime
from src.core.models import OpenOrder, PortfolioState, Position
from src.core.types import OrderSide, OrderType
from src.execution.brokers.simulated import SimulatedBroker
from src.risk.manager import RiskManager


class _StubOrchestrator:
    def run_reconcile(self, context=""):
        return "ok"


class _Provider:
    def get_latest_price(self, symbol):
        return 100.0

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


def _pos(symbol, qty, avg, price):
    p = Position(symbol=symbol, qty=qty, avg_entry_price=avg)
    p.update_price(price)
    return p


# ---- PriceBook TTL (pure) -------------------------------------------------- #

def test_price_book_get_fresh_and_stale(tmp_path):
    rt, _ = _runtime(tmp_path)
    now = datetime.now(timezone.utc)
    rt._price_book["FRESH"] = (123.0, now)
    rt._price_book["STALE"] = (50.0, now - timedelta(seconds=rt._PRICE_TTL_SEC + 5))
    assert rt._price_book_get("FRESH") == 123.0
    assert rt._price_book_get("STALE") is None
    assert rt._price_book_get("MISSING") is None


# ---- account block invested ------------------------------------------------ #

def test_account_block_has_invested():
    ps = PortfolioState(
        cash=1000.0, equity=5000.0,
        positions={"AAPL": _pos("AAPL", 10, 100.0, 120.0)},
    )
    block = SteeringRuntime._account_block(ps)
    assert block["invested"] == 1200.0  # 10 * 120
    assert block["open_pnl"] == 200.0
    assert set(block) == {"equity", "cash", "invested", "open_pnl", "position_count"}


# ---- snapshot enrichment (positions + open_orders) ------------------------- #

def test_publish_snapshot_enriches_positions_and_orders(tmp_path):
    rt, broker = _runtime(tmp_path)
    ps = PortfolioState(
        cash=1000.0, equity=5000.0,
        positions={"AAPL": _pos("AAPL", 10, 100.0, 120.0)},
    )
    opens = [
        # order on a held symbol -> current_price reused from the position
        OpenOrder(order_id="1", symbol="AAPL", side=OrderSide.SELL,
                  order_type=OrderType.STOP, qty=10, stop_price=95.0),
        # order on a symbol we don't hold -> current_price from PriceBook cache
        OpenOrder(order_id="2", symbol="MSFT", side=OrderSide.BUY,
                  order_type=OrderType.LIMIT, qty=5, limit_price=200.0),
    ]
    broker.get_portfolio_state = lambda: ps
    broker.get_open_orders = lambda symbol=None: opens
    rt._price_book["MSFT"] = (210.0, datetime.now(timezone.utc))
    rt.start()
    try:
        rt.publish_snapshot()
        assert _wait(lambda: rt.last_snapshot is not None)
    finally:
        rt.stop()

    snap = rt.last_snapshot
    p = snap["positions"]["AAPL"]
    assert p["current_price"] == 120.0
    assert p["market_value"] == 1200.0
    assert p["unrealized_pnl"] == 200.0

    by_sym = {o["symbol"]: o for o in snap["open_orders"]}
    assert by_sym["AAPL"]["side"] == "sell"
    assert by_sym["AAPL"]["order_type"] == "stop"
    assert by_sym["AAPL"]["current_price"] == 120.0          # reused from held position
    assert by_sym["MSFT"]["current_price"] == 210.0          # from PriceBook
    assert snap["account"]["invested"] == 1200.0
    assert "recent_fills" in snap


# ---- refresh_order_prices: only non-held, missing symbols ------------------ #

def test_refresh_order_prices_fetches_only_unheld_missing(tmp_path):
    rt, broker = _runtime(tmp_path)
    ps = PortfolioState(
        cash=0.0, equity=0.0,
        positions={"AAPL": _pos("AAPL", 10, 100.0, 120.0)},
    )
    opens = [
        OpenOrder(order_id="1", symbol="AAPL", side=OrderSide.SELL,
                  order_type=OrderType.STOP, qty=10, stop_price=95.0),
        OpenOrder(order_id="2", symbol="MSFT", side=OrderSide.BUY,
                  order_type=OrderType.LIMIT, qty=5, limit_price=200.0),
    ]
    calls = []

    def _latest(symbols):
        calls.append(list(symbols))
        return {s: 205.0 for s in symbols if s == "MSFT"}

    broker.get_portfolio_state = lambda: ps
    broker.get_open_orders = lambda symbol=None: opens
    broker.get_latest_prices = _latest
    rt.start()
    try:
        rt.refresh_order_prices()
        assert _wait(lambda: rt._price_book_get("MSFT") == 205.0)
    finally:
        rt.stop()

    # AAPL is held -> never fetched; only MSFT requested
    assert calls == [["MSFT"]]
    assert "AAPL" not in rt._price_book


# ---- refresh_recent_fills: sort desc + cap 8 ------------------------------- #

def test_refresh_recent_fills_sorted_and_capped(tmp_path):
    rt, broker = _runtime(tmp_path)
    base = datetime(2026, 5, 30, 14, 0, tzinfo=timezone.utc)
    fills = [
        FillEvent(fill_id=str(i), symbol="AAPL", qty=1, price=100 + i,
                  side="buy", kind="unknown", ts=base + timedelta(minutes=i))
        for i in range(12)
    ]
    broker.get_fills = lambda since=None: fills
    rt.start()
    try:
        rt.refresh_recent_fills()
        assert _wait(lambda: len(rt._recent_fills) == rt._RECENT_FILLS)
    finally:
        rt.stop()

    rf = rt._recent_fills
    assert len(rf) == 8
    ts = [r["ts"] for r in rf]
    assert ts == sorted(ts, reverse=True)   # newest first
    assert rf[0]["price"] == 111            # i=11 is newest

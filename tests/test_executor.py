from datetime import datetime

import pandas as pd

from src.agent.executor import DecisionExecutor
from src.agent.journal import Decision, Journal
from src.core.models import Order
from src.core.types import OrderClass, OrderSide, OrderType
from src.execution.brokers.simulated import SimulatedBroker
from src.risk.manager import RiskManager


def _ohlcv(n: int = 120, start: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = pd.Series([start + i * 0.5 for i in range(n)], index=idx)
    return pd.DataFrame(
        {"open": close * 0.99, "high": close * 1.01, "low": close * 0.98,
         "close": close, "volume": [1_000_000] * n},
        index=idx,
    )


class _StubProvider:
    """Fixed latest price; synthetic bars; SPY bars with a configurable day-change."""

    def __init__(self, price: float = 100.0, spy_change: float = 0.0):
        self.price = price
        self.spy_change = spy_change
        self._bars = _ohlcv(120)

    def get_latest_price(self, symbol):
        return self.price

    def get_bars(self, symbol, timeframe=None, start=None, end=None, limit=100):
        if symbol == "SPY":
            idx = pd.date_range("2024-01-01", periods=2, freq="D")
            c0, c1 = 500.0, 500.0 * (1 + self.spy_change)
            return pd.DataFrame(
                {"open": [c0, c1], "high": [c0, c1], "low": [c0, c1],
                 "close": [c0, c1], "volume": [1, 1]},
                index=idx,
            )
        return self._bars.tail(limit)


def _make(tmp_path, price=100.0, spy_change=0.0, max_position_pct=0.5):
    broker = SimulatedBroker(initial_capital=100000.0)
    rm = RiskManager(max_position_pct=max_position_pct)
    provider = _StubProvider(price=price, spy_change=spy_change)
    journal = Journal(root=tmp_path / "ws")
    ex = DecisionExecutor(broker, rm, provider, journal=journal, universe=["AAPL", "MSFT"])
    return ex, broker, journal


class TestDecisionExecutor:
    def test_buy_places_resting_bracket(self, tmp_path):
        ex, broker, journal = _make(tmp_path, price=100.0)
        broker.set_current_price("AAPL", 100.0)  # sim needs a price to fill against
        journal.append_decision(Decision(symbol="AAPL", action="BUY", confidence=0.8, stop=95.0, target=120.0))
        outcomes = ex.execute_pending()
        assert outcomes[0].status == "executed"
        pos = broker.get_position("AAPL")
        assert pos is not None and pos.qty > 0
        opens = broker.get_open_orders("AAPL")
        assert any(o.stop_price == 95.0 for o in opens)
        assert any(o.limit_price == 120.0 for o in opens)

    def test_idempotent_across_runs(self, tmp_path):
        ex, broker, journal = _make(tmp_path, price=100.0)
        broker.set_current_price("AAPL", 100.0)
        journal.append_decision(Decision(symbol="AAPL", action="BUY", stop=95.0, target=120.0))
        assert len(ex.execute_pending()) == 1
        assert ex.execute_pending() == []  # cursor advanced; nothing re-executed

    def test_out_of_universe_rejected(self, tmp_path):
        ex, broker, journal = _make(tmp_path)
        journal.append_decision(Decision(symbol="ZZZZ", action="BUY", stop=1.0, target=2.0))
        assert ex.execute_pending()[0].status == "skipped_out_of_universe"

    def test_expired_decision_skipped(self, tmp_path):
        ex, broker, journal = _make(tmp_path)
        journal.append_decision(Decision(
            symbol="AAPL", action="BUY", stop=95.0, target=120.0,
            valid_until=datetime(2020, 1, 1),
        ))
        assert ex.execute_pending()[0].status == "skipped_expired"

    def test_hold_skipped(self, tmp_path):
        ex, broker, journal = _make(tmp_path)
        journal.append_decision(Decision(symbol="AAPL", action="HOLD"))
        assert ex.execute_pending()[0].status == "skipped_hold"

    def test_sell_reduces_position(self, tmp_path):
        ex, broker, journal = _make(tmp_path)
        broker.set_current_price("AAPL", 100.0)
        broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))
        journal.append_decision(Decision(symbol="AAPL", action="SELL", sell_pct=0.5))
        assert ex.execute_pending()[0].status == "executed"
        assert broker.get_position("AAPL").qty == 5

    def test_circuit_breaker_blocks_buy(self, tmp_path):
        ex, broker, journal = _make(tmp_path, price=100.0, spy_change=-0.05)  # market -5%
        broker.set_current_price("AAPL", 100.0)
        journal.append_decision(Decision(symbol="AAPL", action="BUY", stop=95.0, target=120.0))
        out = ex.execute_pending()
        assert out[0].status == "no_order"  # RiskManager halted new buys
        assert broker.get_position("AAPL") is None

    def test_adjust_stop_tightens_and_keeps_target(self, tmp_path):
        ex, broker, journal = _make(tmp_path, price=100.0)
        broker.set_current_price("AAPL", 100.0)
        journal.append_decision(Decision(symbol="AAPL", action="BUY", stop=90.0, target=130.0))
        ex.execute_pending()
        journal.append_decision(Decision(symbol="AAPL", action="ADJUST_STOP", stop=95.0))
        out = ex.execute_pending()
        assert out[-1].status == "executed"
        opens = broker.get_open_orders("AAPL")
        assert any(o.stop_price == 95.0 for o in opens)   # tightened 90 -> 95
        assert any(o.limit_price == 130.0 for o in opens)  # target preserved

    def test_adjust_stop_ratchet_rejects_loosening(self, tmp_path):
        ex, broker, journal = _make(tmp_path, price=100.0)
        broker.set_current_price("AAPL", 100.0)
        journal.append_decision(Decision(symbol="AAPL", action="BUY", stop=90.0, target=130.0))
        ex.execute_pending()
        journal.append_decision(Decision(symbol="AAPL", action="ADJUST_STOP", stop=85.0))  # looser
        ex.execute_pending()
        opens = broker.get_open_orders("AAPL")
        assert any(o.stop_price == 90.0 for o in opens)  # stays at 90 (tighten-only)


class TestRiskExitsBackup:
    def test_skips_position_with_resting_protection(self, tmp_path):
        broker = SimulatedBroker(initial_capital=100000.0)
        broker.set_current_price("AAPL", 100.0)
        broker.submit_order(Order(
            symbol="AAPL", side=OrderSide.BUY, qty=10,
            order_class=OrderClass.BRACKET, take_profit_price=140.0, stop_loss_price=80.0,
        ))
        ex = DecisionExecutor(broker, RiskManager(), _StubProvider(price=92.0),
                              journal=Journal(root=tmp_path / "ws"), universe=["AAPL"])
        # Price -8% (beyond the 5% polled threshold), but a resting stop covers it.
        assert ex.run_risk_exits() == []
        assert broker.get_position("AAPL") is not None

    def test_fires_for_unprotected_position(self, tmp_path):
        broker = SimulatedBroker(initial_capital=100000.0)
        broker.set_current_price("AAPL", 100.0)
        broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))  # no protection
        ex = DecisionExecutor(broker, RiskManager(), _StubProvider(price=92.0),
                              journal=Journal(root=tmp_path / "ws"), universe=["AAPL"])
        filled = ex.run_risk_exits()  # -8% with no resting stop -> backup fires
        assert len(filled) == 1
        assert broker.get_position("AAPL") is None


class TestSimulatedOpenOrders:
    def test_maps_resting_legs(self, tmp_path):
        broker = SimulatedBroker()
        broker.set_current_price("AAPL", 100.0)
        broker.submit_order(Order(
            symbol="AAPL", side=OrderSide.BUY, qty=10,
            order_class=OrderClass.BRACKET, take_profit_price=120.0, stop_loss_price=90.0,
        ))
        opens = broker.get_open_orders("AAPL")
        assert {o.order_type for o in opens} == {OrderType.LIMIT, OrderType.STOP}
        assert all(o.side == OrderSide.SELL for o in opens)

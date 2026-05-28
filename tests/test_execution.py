from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.core.models import Order
from src.core.types import OrderClass, OrderSide, OrderType
from src.core.exceptions import BrokerError
from src.execution.brokers.alpaca_broker import AlpacaBroker, TradingClient
from src.execution.brokers.simulated import SimulatedBroker


class TestSimulatedBroker:
    def setup_method(self):
        self.broker = SimulatedBroker(initial_capital=100000.0, commission_pct=0.001)

    def test_buy_order(self):
        self.broker.set_current_price("AAPL", 150.0)
        order = Order(symbol="AAPL", side=OrderSide.BUY, qty=10)
        filled = self.broker.submit_order(order)
        assert filled.symbol == "AAPL"
        assert filled.qty == 10
        assert filled.filled_price == 150.0

        pos = self.broker.get_position("AAPL")
        assert pos is not None
        assert pos.qty == 10

    def test_sell_order(self):
        self.broker.set_current_price("AAPL", 150.0)
        self.broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))

        self.broker.set_current_price("AAPL", 160.0)
        filled = self.broker.submit_order(
            Order(symbol="AAPL", side=OrderSide.SELL, qty=10)
        )
        assert filled.filled_price == 160.0
        assert self.broker.get_position("AAPL") is None

    def test_insufficient_cash(self):
        self.broker.set_current_price("AAPL", 150.0)
        order = Order(symbol="AAPL", side=OrderSide.BUY, qty=1000)
        with pytest.raises(BrokerError, match="Insufficient cash"):
            self.broker.submit_order(order)

    def test_sell_without_position(self):
        self.broker.set_current_price("AAPL", 150.0)
        order = Order(symbol="AAPL", side=OrderSide.SELL, qty=10)
        with pytest.raises(BrokerError, match="No position"):
            self.broker.submit_order(order)

    def test_portfolio_state(self):
        self.broker.set_current_price("AAPL", 150.0)
        self.broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))
        state = self.broker.get_portfolio_state()
        assert state.cash < 100000.0
        assert state.equity == pytest.approx(100000.0 - 1500 * 0.001, abs=1)
        assert "AAPL" in state.positions

    def test_reset(self):
        self.broker.set_current_price("AAPL", 150.0)
        self.broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))
        self.broker.reset()
        state = self.broker.get_portfolio_state()
        assert state.cash == 100000.0
        assert len(state.positions) == 0

    def test_commission_applied(self):
        self.broker.set_current_price("AAPL", 100.0)
        self.broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))
        # Cost = 1000 + 1000*0.001 = 1001
        state = self.broker.get_portfolio_state()
        assert state.cash == pytest.approx(100000.0 - 1001.0)

    def test_close_position(self):
        self.broker.set_current_price("AAPL", 100.0)
        self.broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))
        filled = self.broker.close_position("AAPL")
        assert filled is not None
        assert filled.qty == 10
        assert self.broker.get_position("AAPL") is None

    def test_get_order_status_returns_fill(self):
        self.broker.set_current_price("AAPL", 150.0)
        filled = self.broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))
        assert self.broker.get_order_status(filled.order_id) == filled
        assert self.broker.get_order_status("does_not_exist") is None


class TestOrderModel:
    def test_bracket_requires_both_legs(self):
        with pytest.raises(ValidationError):
            Order(
                symbol="AAPL", side=OrderSide.BUY, qty=10,
                order_class=OrderClass.BRACKET, take_profit_price=120.0,
            )

    def test_simple_order_needs_no_legs(self):
        order = Order(symbol="AAPL", side=OrderSide.BUY, qty=10)
        assert order.order_class == OrderClass.SIMPLE


class TestSimulatedBracketOrders:
    def setup_method(self):
        self.broker = SimulatedBroker(initial_capital=100000.0, commission_pct=0.0)

    def _bracket(self, **kw):
        defaults = dict(
            symbol="AAPL", side=OrderSide.BUY, qty=10,
            order_class=OrderClass.BRACKET, take_profit_price=120.0, stop_loss_price=90.0,
        )
        defaults.update(kw)
        return Order(**defaults)

    def test_market_entry_fills_and_arms_protection(self):
        self.broker.set_current_price("AAPL", 100.0)
        entry = self.broker.submit_order(self._bracket())
        assert entry.side == OrderSide.BUY
        assert entry.filled_price == 100.0
        assert self.broker.get_position("AAPL").qty == 10
        # Two resting protective legs are now armed.
        assert len(self.broker._resting["AAPL"]) == 2

    def test_take_profit_triggers_and_cancels_stop(self):
        self.broker.set_current_price("AAPL", 100.0)
        self.broker.submit_order(self._bracket())
        # Rally: bar high crosses the take-profit.
        self.broker.set_current_price("AAPL", 121.0, high=121.0, low=119.0)
        assert self.broker.get_position("AAPL") is None
        # Sold 10 @ 120 take-profit: 100000 - 1000 + 1200.
        assert self.broker.get_portfolio_state().cash == pytest.approx(100200.0)
        assert "AAPL" not in self.broker._resting  # OCO sibling cancelled

    def test_stop_loss_triggers_and_cancels_take_profit(self):
        self.broker.set_current_price("AAPL", 100.0)
        self.broker.submit_order(self._bracket())
        # Drop: bar low crosses the stop.
        self.broker.set_current_price("AAPL", 89.0, high=95.0, low=89.0)
        assert self.broker.get_position("AAPL") is None
        # Sold 10 @ 90 stop: 100000 - 1000 + 900.
        assert self.broker.get_portfolio_state().cash == pytest.approx(99900.0)

    def test_both_sides_bar_stops_out_first(self):
        self.broker.set_current_price("AAPL", 100.0)
        self.broker.submit_order(self._bracket())
        # A bar straddling both legs resolves adversely (stop wins).
        self.broker.set_current_price("AAPL", 100.0, high=121.0, low=89.0)
        assert self.broker.get_position("AAPL") is None
        assert self.broker.get_portfolio_state().cash == pytest.approx(99900.0)

    def test_limit_entry_rests_then_fills_and_protects(self):
        self.broker.set_current_price("AAPL", 100.0)
        pending = self.broker.submit_order(
            self._bracket(order_type=OrderType.LIMIT, limit_price=95.0)
        )
        assert pending.qty == 0  # resting, not filled at 100
        assert self.broker.get_position("AAPL") is None
        # Dip to the limit fills the entry and arms protection.
        self.broker.set_current_price("AAPL", 95.0, high=99.0, low=94.0)
        assert self.broker.get_position("AAPL").qty == 10
        # Then a rally takes profit.
        self.broker.set_current_price("AAPL", 121.0, high=121.0, low=120.0)
        assert self.broker.get_position("AAPL") is None

    def test_oco_protects_existing_position(self):
        self.broker.set_current_price("AAPL", 100.0)
        self.broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))
        oco = self.broker.submit_order(Order(
            symbol="AAPL", side=OrderSide.SELL, qty=10,
            order_class=OrderClass.OCO, take_profit_price=120.0, stop_loss_price=90.0,
        ))
        assert oco.qty == 0  # nothing fills immediately
        self.broker.set_current_price("AAPL", 91.0, high=91.0, low=89.0)
        assert self.broker.get_position("AAPL") is None

    def test_cancel_removes_resting_group(self):
        self.broker.set_current_price("AAPL", 100.0)
        self.broker.submit_order(self._bracket())
        leg_id = self.broker._resting["AAPL"][0].leg_id
        assert self.broker.cancel_order(leg_id) is True
        assert "AAPL" not in self.broker._resting
        # Old take-profit level no longer sells the position.
        self.broker.set_current_price("AAPL", 121.0, high=121.0, low=120.0)
        assert self.broker.get_position("AAPL").qty == 10

    def test_cancel_oco_by_returned_id(self):
        self.broker.set_current_price("AAPL", 100.0)
        self.broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))
        oco = self.broker.submit_order(Order(
            symbol="AAPL", side=OrderSide.SELL, qty=10,
            order_class=OrderClass.OCO, take_profit_price=120.0, stop_loss_price=90.0,
        ))
        # The id returned for a resting OCO must itself be cancellable.
        assert self.broker.cancel_order(oco.order_id) is True
        assert "AAPL" not in self.broker._resting
        # Protection is gone: a drop no longer sells.
        self.broker.set_current_price("AAPL", 89.0, high=91.0, low=89.0)
        assert self.broker.get_position("AAPL").qty == 10


@pytest.mark.skipif(TradingClient is None, reason="alpaca-py not installed")
class TestAlpacaClockRetry:
    def _broker(self):
        return AlpacaBroker(api_key="x", secret_key="y", paper=True)

    def test_retries_then_succeeds(self):
        broker = self._broker()
        calls = {"n": 0}

        class _FlakyClient:
            def get_clock(self):
                calls["n"] += 1
                if calls["n"] < 3:
                    raise RuntimeError("connection aborted")
                return SimpleNamespace(is_open=True)

        broker._client = _FlakyClient()
        assert broker.is_market_open(retries=3, delay=0.0) is True
        assert calls["n"] == 3  # retried past the transient failures

    def test_fails_closed_after_all_retries(self):
        broker = self._broker()

        class _DeadClient:
            def get_clock(self):
                raise RuntimeError("down")

        broker._client = _DeadClient()
        assert broker.is_market_open(retries=2, delay=0.0) is False


# Trade-ledger reconstruction is on BaseBroker (default no-op) and overridden
# only by AlpacaBroker -- so callers stay broker-agnostic instead of doing
# ``getattr(broker, "_client", None)`` to detect Alpaca (AI-DLC S-4).
class TestTradeLedgerPort:
    def test_default_is_noop_for_simulated(self, tmp_path):
        broker = SimulatedBroker(initial_capital=10000.0)
        target = tmp_path / "trades.jsonl"
        # No-op: doesn't raise, doesn't create the file.
        broker.record_trade_ledger(target, since="2024-01-01", min_notional=10.0)
        assert not target.exists()

    @pytest.mark.skipif(TradingClient is None, reason="alpaca-py not installed")
    def test_alpaca_delegates_to_record_trades(self, monkeypatch, tmp_path):
        from src.execution.brokers import alpaca_broker

        captured = {}
        def _fake_record_trades(client, path, since=None, min_notional=0.0):
            captured.update(
                client=client, path=path, since=since, min_notional=min_notional,
            )
        monkeypatch.setattr(alpaca_broker, "record_trades", _fake_record_trades)

        broker = AlpacaBroker(api_key="x", secret_key="y", paper=True)
        sentinel = object()
        broker._client = sentinel  # avoid any real API client identity in the assert

        target = tmp_path / "trades.jsonl"
        broker.record_trade_ledger(target, since="2026-01-01", min_notional=1.5)

        assert captured["client"] is sentinel
        assert captured["path"] == target
        assert captured["since"] == "2026-01-01"
        assert captured["min_notional"] == 1.5

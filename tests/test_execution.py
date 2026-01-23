import pytest

from src.core.models import Order
from src.core.types import OrderSide
from src.core.exceptions import BrokerError
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

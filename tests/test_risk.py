import pytest
from pydantic import ValidationError

from src.core.models import Order, PortfolioState, Position, TradeSignal
from src.core.types import OrderSide, Signal
from src.risk.manager import RiskManager
from src.risk.position_sizer import PositionSizer


class TestTradeSignal:
    def test_sell_pct_default_is_full_position(self):
        """Test that sell_pct defaults to 1.0 (full position)."""
        signal = TradeSignal(symbol="AAPL", signal=Signal.SELL)
        assert signal.sell_pct == 1.0

    def test_sell_pct_valid_range(self):
        """Test sell_pct accepts values in valid range."""
        signal = TradeSignal(symbol="AAPL", signal=Signal.SELL, sell_pct=0.5)
        assert signal.sell_pct == 0.5

    def test_sell_pct_boundary_zero(self):
        """Test sell_pct accepts 0.0 boundary."""
        signal = TradeSignal(symbol="AAPL", signal=Signal.SELL, sell_pct=0.0)
        assert signal.sell_pct == 0.0

    def test_sell_pct_boundary_one(self):
        """Test sell_pct accepts 1.0 boundary."""
        signal = TradeSignal(symbol="AAPL", signal=Signal.SELL, sell_pct=1.0)
        assert signal.sell_pct == 1.0

    def test_sell_pct_rejects_negative(self):
        """Test sell_pct rejects negative values."""
        with pytest.raises(ValidationError):
            TradeSignal(symbol="AAPL", signal=Signal.SELL, sell_pct=-0.1)

    def test_sell_pct_rejects_over_one(self):
        """Test sell_pct rejects values over 1.0."""
        with pytest.raises(ValidationError):
            TradeSignal(symbol="AAPL", signal=Signal.SELL, sell_pct=1.5)


class TestPositionSizer:
    def test_basic_sizing(self):
        sizer = PositionSizer(max_position_pct=0.1, max_portfolio_risk=0.02)
        portfolio = PortfolioState(cash=100000, equity=100000)
        shares = sizer.calculate_shares("AAPL", 150.0, portfolio, confidence=1.0)
        # Max allocation = 10% of 100k = 10k, 10k/150 = 66 shares
        assert shares > 0
        assert shares <= 66

    def test_zero_price(self):
        sizer = PositionSizer()
        portfolio = PortfolioState(cash=100000, equity=100000)
        assert sizer.calculate_shares("AAPL", 0.0, portfolio) == 0

    def test_respects_cash_limit(self):
        sizer = PositionSizer(max_position_pct=0.5)
        portfolio = PortfolioState(cash=1000, equity=100000)
        shares = sizer.calculate_shares("AAPL", 150.0, portfolio, confidence=1.0)
        assert shares * 150 <= 1000


class TestRiskManager:
    def setup_method(self):
        self.rm = RiskManager(
            max_position_pct=0.1,
            max_portfolio_risk=0.02,
            stop_loss_pct=0.05,
            take_profit_pct=0.15,
            max_open_positions=3,
        )

    def test_buy_signal_creates_order(self):
        signal = TradeSignal(symbol="AAPL", signal=Signal.BUY, confidence=0.8)
        portfolio = PortfolioState(cash=100000, equity=100000)
        order = self.rm.evaluate_signal(signal, 150.0, portfolio)
        assert order is not None
        assert order.side == OrderSide.BUY
        assert order.qty > 0

    def test_hold_signal_returns_none(self):
        signal = TradeSignal(symbol="AAPL", signal=Signal.HOLD, confidence=0.5)
        portfolio = PortfolioState(cash=100000, equity=100000)
        order = self.rm.evaluate_signal(signal, 150.0, portfolio)
        assert order is None

    def test_max_positions_blocks_buy(self):
        signal = TradeSignal(symbol="NEW", signal=Signal.BUY, confidence=0.8)
        positions = {
            f"SYM{i}": Position(symbol=f"SYM{i}", qty=10, avg_entry_price=100)
            for i in range(3)
        }
        portfolio = PortfolioState(cash=100000, equity=130000, positions=positions)
        order = self.rm.evaluate_signal(signal, 150.0, portfolio)
        assert order is None

    def test_sell_existing_position(self):
        signal = TradeSignal(symbol="AAPL", signal=Signal.SELL, confidence=0.7)
        portfolio = PortfolioState(
            cash=50000,
            equity=65000,
            positions={"AAPL": Position(symbol="AAPL", qty=100, avg_entry_price=150)},
        )
        order = self.rm.evaluate_signal(signal, 140.0, portfolio)
        assert order is not None
        assert order.side == OrderSide.SELL
        assert order.qty == 100

    def test_stop_loss_trigger(self):
        pos = Position(symbol="AAPL", qty=10, avg_entry_price=100.0, current_price=94.0)
        portfolio = PortfolioState(cash=50000, equity=50940, positions={"AAPL": pos})
        orders = self.rm.check_stop_loss(portfolio)
        assert len(orders) == 1
        assert orders[0].symbol == "AAPL"

    def test_take_profit_trigger(self):
        pos = Position(symbol="AAPL", qty=10, avg_entry_price=100.0, current_price=116.0)
        portfolio = PortfolioState(cash=50000, equity=51160, positions={"AAPL": pos})
        orders = self.rm.check_take_profit(portfolio)
        assert len(orders) == 1

    def test_partial_sell_50_percent(self):
        """Test partial sell: 50% of position."""
        signal = TradeSignal(symbol="AAPL", signal=Signal.SELL, confidence=0.7, sell_pct=0.5)
        portfolio = PortfolioState(
            cash=50000,
            equity=65000,
            positions={"AAPL": Position(symbol="AAPL", qty=100, avg_entry_price=150)},
        )
        order = self.rm.evaluate_signal(signal, 140.0, portfolio)
        assert order is not None
        assert order.side == OrderSide.SELL
        assert order.qty == 50  # 50% of 100 shares

    def test_partial_sell_30_percent(self):
        """Test partial sell: 30% of position."""
        signal = TradeSignal(symbol="AAPL", signal=Signal.SELL, confidence=0.7, sell_pct=0.3)
        portfolio = PortfolioState(
            cash=50000,
            equity=65000,
            positions={"AAPL": Position(symbol="AAPL", qty=100, avg_entry_price=150)},
        )
        order = self.rm.evaluate_signal(signal, 140.0, portfolio)
        assert order is not None
        assert order.qty == 30  # 30% of 100 shares

    def test_partial_sell_zero_percent_sells_minimum(self):
        """Test edge case: sell_pct=0 should sell at least 1 share."""
        signal = TradeSignal(symbol="AAPL", signal=Signal.SELL, confidence=0.7, sell_pct=0.0)
        portfolio = PortfolioState(
            cash=50000,
            equity=65000,
            positions={"AAPL": Position(symbol="AAPL", qty=100, avg_entry_price=150)},
        )
        order = self.rm.evaluate_signal(signal, 140.0, portfolio)
        assert order is not None
        assert order.qty == 1  # Minimum 1 share

    def test_partial_sell_small_position(self):
        """Test partial sell with small position rounds to at least 1 share."""
        signal = TradeSignal(symbol="AAPL", signal=Signal.SELL, confidence=0.7, sell_pct=0.3)
        portfolio = PortfolioState(
            cash=50000,
            equity=51500,
            positions={"AAPL": Position(symbol="AAPL", qty=2, avg_entry_price=150)},
        )
        order = self.rm.evaluate_signal(signal, 150.0, portfolio)
        assert order is not None
        # 30% of 2 shares = 0.6, rounded to 0, but minimum is 1
        assert order.qty == 1

import pytest
from pydantic import ValidationError

from src.core.models import Order, PortfolioState, Position, TradeSignal
from src.core.types import OrderClass, OrderSide, OrderType, Signal
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

    def test_partial_sell_zero_percent_returns_no_order(self):
        """sell_pct=0 means sell nothing -> no order. (The old code wrongly forced
        a 1-share sell, which could oversell a small/fractional position.)"""
        signal = TradeSignal(symbol="AAPL", signal=Signal.SELL, confidence=0.7, sell_pct=0.0)
        portfolio = PortfolioState(
            cash=50000,
            equity=65000,
            positions={"AAPL": Position(symbol="AAPL", qty=100, avg_entry_price=150)},
        )
        order = self.rm.evaluate_signal(signal, 140.0, portfolio)
        assert order is None

    def test_partial_sell_keeps_fractional(self):
        """Partial sell keeps fractional sizing (Alpaca supports fractional shares)
        instead of rounding up to a whole share, which oversold the intent."""
        signal = TradeSignal(symbol="AAPL", signal=Signal.SELL, confidence=0.7, sell_pct=0.3)
        portfolio = PortfolioState(
            cash=50000,
            equity=51500,
            positions={"AAPL": Position(symbol="AAPL", qty=2, avg_entry_price=150)},
        )
        order = self.rm.evaluate_signal(signal, 150.0, portfolio)
        assert order is not None
        assert order.qty == pytest.approx(0.6)  # 30% of 2 shares, fractional

    def test_full_sell_of_fractional_position_is_exact(self):
        """Full exit (sell_pct=1.0) of a sub-1-share position sells the EXACT
        held quantity -- the old int()+min-1 tried to sell 1 share of 0.5 held,
        which the broker would reject/oversell."""
        signal = TradeSignal(symbol="AAPL", signal=Signal.SELL, sell_pct=1.0)
        portfolio = PortfolioState(
            cash=50000,
            equity=50050,
            positions={"AAPL": Position(symbol="AAPL", qty=0.5, avg_entry_price=100)},
        )
        order = self.rm.evaluate_signal(signal, 100.0, portfolio)
        assert order is not None
        assert order.qty == pytest.approx(0.5)  # exact, not rounded up to 1


class TestRiskManagerBracket:
    def setup_method(self):
        self.rm = RiskManager(
            max_position_pct=0.1,
            max_portfolio_risk=0.02,
            max_open_positions=10,
            max_stop_distance_pct=0.12,
            atr_stop_multiple=3.0,
            default_risk_reward=2.5,
            use_bracket_orders=True,
        )

    def _buy(self, **levels):
        key_levels = {k: levels.get(k) for k in ("entry", "stop_loss", "take_profit")}
        metadata = {"key_levels": key_levels}
        if "atr" in levels:
            metadata["atr"] = levels["atr"]
        return TradeSignal(symbol="AAPL", signal=Signal.BUY, confidence=1.0, metadata=metadata)

    def test_explicit_levels_build_bracket(self):
        portfolio = PortfolioState(cash=100000, equity=100000)
        order = self.rm.evaluate_signal(
            self._buy(entry=100, stop_loss=95, take_profit=120), 100.0, portfolio
        )
        assert order is not None
        assert order.order_class == OrderClass.BRACKET
        assert order.stop_loss_price == 95.0
        assert order.take_profit_price == 120.0
        assert order.order_type == OrderType.MARKET  # entry == current price
        assert order.qty > 0

    def test_stop_distance_clamped_to_max(self):
        portfolio = PortfolioState(cash=100000, equity=100000)
        # stop 20% away -> clamped to the 12% max (88.0)
        order = self.rm.evaluate_signal(
            self._buy(entry=100, stop_loss=80, take_profit=130), 100.0, portfolio
        )
        assert order.stop_loss_price == 88.0

    def test_atr_stop_when_no_explicit_level(self):
        portfolio = PortfolioState(cash=100000, equity=100000)
        # No stop level; atr=2 -> stop = 100 - 3*2 = 94, target = 100 + 2.5*6 = 115
        order = self.rm.evaluate_signal(self._buy(entry=100, atr=2.0), 100.0, portfolio)
        assert order is not None
        assert order.order_class == OrderClass.BRACKET
        assert order.stop_loss_price == 94.0
        assert order.take_profit_price == 115.0

    def test_target_derived_from_risk_reward(self):
        portfolio = PortfolioState(cash=100000, equity=100000)
        # No target; derived = 100 + 2.5*(100-96) = 110
        order = self.rm.evaluate_signal(self._buy(entry=100, stop_loss=96), 100.0, portfolio)
        assert order.take_profit_price == 110.0

    def test_limit_entry_when_entry_below_price(self):
        portfolio = PortfolioState(cash=100000, equity=100000)
        order = self.rm.evaluate_signal(
            self._buy(entry=95, stop_loss=90, take_profit=115), 100.0, portfolio
        )
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == 95.0

    def test_no_stop_source_falls_back_to_simple_buy(self):
        portfolio = PortfolioState(cash=100000, equity=100000)
        order = self.rm.evaluate_signal(
            self._buy(entry=100, take_profit=120), 100.0, portfolio
        )
        assert order is not None
        assert order.order_class == OrderClass.SIMPLE
        assert order.qty > 0

    def test_stop_distance_sizing_normalizes_risk(self):
        # With a loose position cap, a tighter stop -> larger position and the
        # per-trade dollar risk stays ~constant (max_portfolio_risk binds).
        rm = RiskManager(
            max_position_pct=0.5, max_portfolio_risk=0.02,
            max_stop_distance_pct=0.20, use_bracket_orders=True,
        )
        p = PortfolioState(cash=100000, equity=100000)
        tight = rm.evaluate_signal(self._buy(entry=100, stop_loss=95, take_profit=130), 100.0, p)
        wide = rm.evaluate_signal(self._buy(entry=100, stop_loss=90, take_profit=130), 100.0, p)
        assert tight.qty > wide.qty
        assert tight.qty * (100 - 95) == pytest.approx(2000, rel=0.02)
        assert wide.qty * (100 - 90) == pytest.approx(2000, rel=0.02)

    def test_brackets_disabled_by_default(self):
        rm = RiskManager()  # use_bracket_orders defaults to False
        p = PortfolioState(cash=100000, equity=100000)
        order = rm.evaluate_signal(
            self._buy(entry=100, stop_loss=95, take_profit=120), 100.0, p
        )
        assert order.order_class == OrderClass.SIMPLE


class TestCircuitBreaker:
    def _buy(self):
        return TradeSignal(symbol="AAPL", signal=Signal.BUY, confidence=0.9)

    def test_halt_blocks_new_buys(self):
        rm = RiskManager(market_halt_threshold_pct=-0.03)
        rm.update_market_halt(-0.05)  # market down 5% -> below -3% threshold
        assert rm.new_buys_halted is True
        p = PortfolioState(cash=100000, equity=100000)
        assert rm.evaluate_signal(self._buy(), 100.0, p) is None

    def test_no_halt_above_threshold(self):
        rm = RiskManager(market_halt_threshold_pct=-0.03)
        rm.update_market_halt(-0.01)
        assert rm.new_buys_halted is False
        p = PortfolioState(cash=100000, equity=100000)
        assert rm.evaluate_signal(self._buy(), 100.0, p) is not None

    def test_halt_clears_when_market_recovers(self):
        rm = RiskManager(market_halt_threshold_pct=-0.03)
        rm.update_market_halt(-0.05)
        rm.update_market_halt(0.01)
        assert rm.new_buys_halted is False


class TestProtectedSymbolsBackup:
    def test_protected_symbol_skipped_in_stop_check(self):
        rm = RiskManager(stop_loss_pct=0.05)
        pos = Position(symbol="AAPL", qty=10, avg_entry_price=100.0, current_price=90.0)
        p = PortfolioState(cash=50000, equity=50900, positions={"AAPL": pos})
        assert len(rm.check_stop_loss(p)) == 1  # unprotected -> polled stop fires
        assert rm.check_stop_loss(p, protected_symbols={"AAPL"}) == []  # resting -> skip

    def test_protected_symbol_skipped_in_take_profit(self):
        rm = RiskManager(take_profit_pct=0.15)
        pos = Position(symbol="AAPL", qty=10, avg_entry_price=100.0, current_price=120.0)
        p = PortfolioState(cash=50000, equity=51200, positions={"AAPL": pos})
        assert len(rm.check_take_profit(p)) == 1
        assert rm.check_take_profit(p, protected_symbols={"AAPL"}) == []


class TestRatchetStop:
    def test_only_tightens_by_default(self):
        rm = RiskManager()
        assert rm.ratchet_stop(95.0, 97.0) == 97.0  # raising a long stop = tighten
        assert rm.ratchet_stop(95.0, 92.0) == 95.0  # lowering rejected

    def test_allow_widen_overrides(self):
        rm = RiskManager()
        assert rm.ratchet_stop(95.0, 92.0, allow_widen=True) == 92.0

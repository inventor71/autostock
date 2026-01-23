import pytest

from src.core.types import Signal, OrderSide, TimeFrame, TradingMode
from src.core.models import Bar, TradeSignal, Position, PortfolioState, Order
from src.core.exceptions import AutostockError, DataProviderError, RiskLimitError


class TestTypes:
    def test_signal_values(self):
        assert Signal.BUY == "BUY"
        assert Signal.SELL == "SELL"
        assert Signal.HOLD == "HOLD"

    def test_timeframe_values(self):
        assert TimeFrame.DAY_1 == "1d"
        assert TimeFrame.HOUR_1 == "1h"


class TestModels:
    def test_trade_signal(self):
        sig = TradeSignal(
            symbol="AAPL",
            signal=Signal.BUY,
            confidence=0.8,
            strategy_name="test",
        )
        assert sig.symbol == "AAPL"
        assert sig.signal == Signal.BUY
        assert sig.confidence == 0.8

    def test_position_update_price(self):
        pos = Position(symbol="AAPL", qty=10, avg_entry_price=150.0)
        pos.update_price(160.0)
        assert pos.current_price == 160.0
        assert pos.market_value == 1600.0
        assert pos.unrealized_pnl == 100.0

    def test_portfolio_state(self):
        pos = Position(
            symbol="AAPL", qty=10, avg_entry_price=150.0,
            current_price=160.0, market_value=1600.0,
        )
        portfolio = PortfolioState(
            cash=50000.0,
            equity=51600.0,
            positions={"AAPL": pos},
        )
        assert portfolio.position_count == 1
        assert portfolio.total_value == 51600.0


class TestExceptions:
    def test_exception_hierarchy(self):
        assert issubclass(DataProviderError, AutostockError)
        assert issubclass(RiskLimitError, AutostockError)

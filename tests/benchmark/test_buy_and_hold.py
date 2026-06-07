import pandas as pd
import pytest

from src.core.exceptions import InsufficientDataError
from src.core.models import PortfolioState, Position
from src.core.types import Signal
from src.strategy.buy_and_hold import BuyAndHoldStrategy


def make_bars(n: int = 3) -> pd.DataFrame:
    return pd.DataFrame(
        {"open": [100.0] * n, "high": [101.0] * n, "low": [99.0] * n,
         "close": [100.0] * n, "volume": [1_000_000] * n},
        index=pd.date_range("2023-01-01", periods=n, freq="D"),
    )


def test_buy_when_not_held():
    s = BuyAndHoldStrategy()
    sig = s.generate_signal("AAPL", make_bars(), portfolio=None)
    assert sig.signal == Signal.BUY
    assert sig.confidence == 1.0


def test_hold_when_already_held():
    s = BuyAndHoldStrategy()
    pos = Position(symbol="AAPL", qty=10, avg_entry_price=100.0)
    pf = PortfolioState(cash=0.0, equity=1000.0, positions={"AAPL": pos})
    sig = s.generate_signal("AAPL", make_bars(), portfolio=pf)
    assert sig.signal == Signal.HOLD


def test_buy_when_portfolio_has_other_symbol():
    s = BuyAndHoldStrategy()
    pos = Position(symbol="MSFT", qty=10, avg_entry_price=100.0)
    pf = PortfolioState(cash=500.0, equity=1500.0, positions={"MSFT": pos})
    sig = s.generate_signal("AAPL", make_bars(), portfolio=pf)
    assert sig.signal == Signal.BUY


def test_empty_bars_raises():
    s = BuyAndHoldStrategy()
    with pytest.raises(InsufficientDataError):
        s.generate_signal("AAPL", make_bars(0))


def test_registered():
    from src.strategy.registry import create_strategy

    s = create_strategy("buy_and_hold", {})
    assert isinstance(s, BuyAndHoldStrategy)
    assert s.name == "buy_and_hold"

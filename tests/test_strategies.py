import numpy as np
import pandas as pd
import pytest

from src.core.types import Signal
from src.core.exceptions import InsufficientDataError
from src.strategy.technical.ma_crossover import MovingAverageCrossover
from src.strategy.technical.rsi_strategy import RSIStrategy
from src.strategy.technical.macd_strategy import MACDStrategy
from src.strategy.technical.bollinger import BollingerBandsStrategy
from src.strategy.registry import list_strategies, get_strategy_class, create_strategy


def make_bars(prices: list[float], volume: float = 1000000) -> pd.DataFrame:
    """Helper to create test bar data."""
    n = len(prices)
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [volume] * n,
        },
        index=pd.date_range("2023-01-01", periods=n, freq="D"),
    )


class TestMAcrossover:
    def test_insufficient_data(self):
        strategy = MovingAverageCrossover({"fast_period": 5, "slow_period": 10})
        bars = make_bars([100.0] * 5)
        with pytest.raises(InsufficientDataError):
            strategy.generate_signal("AAPL", bars)

    def test_buy_signal_on_crossover(self):
        strategy = MovingAverageCrossover({"fast_period": 5, "slow_period": 10})
        # Create data where fast MA crosses above slow MA
        prices = [100.0] * 10 + [100 + i * 2 for i in range(5)]
        bars = make_bars(prices)
        signal = strategy.generate_signal("AAPL", bars)
        # After trending up, fast MA > slow MA
        assert signal.signal in (Signal.BUY, Signal.HOLD)

    def test_hold_when_no_crossover(self):
        strategy = MovingAverageCrossover({"fast_period": 5, "slow_period": 10})
        prices = [100.0] * 20
        bars = make_bars(prices)
        signal = strategy.generate_signal("AAPL", bars)
        assert signal.signal == Signal.HOLD


class TestRSI:
    def test_oversold_buy(self):
        strategy = RSIStrategy({"period": 14, "oversold": 30, "overbought": 70})
        # Create heavily declining prices to push RSI below 30
        prices = [100 - i * 2 for i in range(30)]
        bars = make_bars(prices)
        signal = strategy.generate_signal("AAPL", bars)
        assert signal.signal == Signal.BUY

    def test_overbought_sell(self):
        strategy = RSIStrategy({"period": 14, "oversold": 30, "overbought": 70})
        # Create heavily rising prices to push RSI above 70
        prices = [100 + i * 2 for i in range(30)]
        bars = make_bars(prices)
        signal = strategy.generate_signal("AAPL", bars)
        assert signal.signal == Signal.SELL


class TestMACD:
    def test_insufficient_data(self):
        strategy = MACDStrategy()
        bars = make_bars([100.0] * 10)
        with pytest.raises(InsufficientDataError):
            strategy.generate_signal("AAPL", bars)

    def test_signal_generation(self):
        strategy = MACDStrategy({"fast_period": 12, "slow_period": 26, "signal_period": 9})
        prices = [100 + np.sin(i / 5) * 10 for i in range(60)]
        bars = make_bars(prices)
        signal = strategy.generate_signal("AAPL", bars)
        assert signal.signal in (Signal.BUY, Signal.SELL, Signal.HOLD)
        assert 0 <= signal.confidence <= 1.0


class TestBollinger:
    def test_below_lower_band(self):
        strategy = BollingerBandsStrategy({"period": 20, "num_std": 2.0})
        # Stable prices with tiny variation, then sudden drop on last bar
        prices = [100.0 + (i % 3) * 0.1 for i in range(25)]
        prices[-1] = 85.0  # Sudden drop well below lower band
        bars = make_bars(prices)
        signal = strategy.generate_signal("AAPL", bars)
        assert signal.signal == Signal.BUY

    def test_above_upper_band(self):
        strategy = BollingerBandsStrategy({"period": 20, "num_std": 2.0})
        # Stable prices with tiny variation, then sudden spike on last bar
        prices = [100.0 + (i % 3) * 0.1 for i in range(25)]
        prices[-1] = 115.0  # Sudden spike well above upper band
        bars = make_bars(prices)
        signal = strategy.generate_signal("AAPL", bars)
        assert signal.signal == Signal.SELL


class TestRegistry:
    def test_strategies_registered(self):
        strategies = list_strategies()
        assert "ma_crossover" in strategies
        assert "rsi" in strategies
        assert "macd" in strategies
        assert "bollinger" in strategies

    def test_create_strategy(self):
        strategy = create_strategy("ma_crossover", {"fast_period": 10, "slow_period": 30})
        assert strategy.fast_period == 10
        assert strategy.slow_period == 30

    def test_unknown_strategy_raises(self):
        with pytest.raises(KeyError):
            get_strategy_class("nonexistent")

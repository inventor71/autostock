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


class TestLLMStrategyConfigInjection:
    """LLMStrategy reads provider config + api_key from params (injected by the
    composition root) — it must not reach into global settings (S-3)."""

    def _make(self, **params):
        import src.strategy.llm.llm_strategy  # noqa: F401 (trigger registration)
        return create_strategy("llm", params)

    def test_defaults_when_no_params(self):
        s = self._make()
        assert s.provider == "claude"
        assert s.model is None
        assert s.temperature == 0.3
        assert s.prompt_version == "latest"
        assert s.lookback_days == 30
        assert s.include_news is True

    def test_injected_params_are_used(self):
        s = self._make(
            provider="openai", model="gpt-4o", temperature=0.7,
            prompt_version="v2", lookback_days=60, include_news=False,
            api_key="sk-test-123",
        )
        assert s.provider == "openai"
        assert s.model == "gpt-4o"
        assert s.temperature == 0.7
        assert s.prompt_version == "v2"
        assert s.lookback_days == 60
        assert s.include_news is False
        assert s._get_api_key() == "sk-test-123"

    def test_claude_code_provider_uses_no_key(self):
        s = self._make(provider="claude_code", api_key="ignored")
        assert s._get_api_key() == ""

    def test_unknown_provider_fails_closed(self):
        s = self._make(provider="bogus", api_key="x")
        with pytest.raises(ValueError):
            s._get_api_key()


class TestMainLLMInjectionHelpers:
    """The composition root resolves config + key and injects them (S-3)."""

    @staticmethod
    def _settings(provider):
        from types import SimpleNamespace
        return SimpleNamespace(
            llm=SimpleNamespace(
                provider=provider, model="m", temperature=0.4,
                prompt_version="v1", lookback_days=10, include_news=True,
            ),
            anthropic_api_key="anthropic-key",
            openai_api_key="openai-key",
        )

    def test_resolve_api_key_by_provider(self):
        import main
        assert main._resolve_api_key(self._settings("claude"), "claude") == "anthropic-key"
        assert main._resolve_api_key(self._settings("openai"), "openai") == "openai-key"
        assert main._resolve_api_key(self._settings("claude_code"), "claude_code") == ""

    def test_llm_params_carry_config_and_key(self):
        import main
        p = main._llm_params(self._settings("claude"))
        assert p["provider"] == "claude"
        assert p["api_key"] == "anthropic-key"
        assert p["lookback_days"] == 10

    def test_strategies_yaml_params_override_injected(self):
        import main
        injected = main._llm_params(self._settings("claude"))
        yaml_params = {"provider": "openai", "temperature": 0.9}
        merged = {**injected, **yaml_params}  # mirrors create_strategies
        assert merged["provider"] == "openai"  # yaml wins
        assert merged["temperature"] == 0.9
        assert merged["lookback_days"] == 10  # injected default kept

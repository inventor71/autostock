from __future__ import annotations

import pandas as pd
from loguru import logger

from src.core.exceptions import InsufficientDataError
from src.core.models import PortfolioState, TradeSignal
from src.core.types import Signal
from src.strategy.base import BaseStrategy
from src.strategy.registry import register_strategy


@register_strategy("ma_crossover")
class MovingAverageCrossover(BaseStrategy):
    """Moving Average Crossover strategy.

    Generates BUY when fast MA crosses above slow MA,
    SELL when fast MA crosses below slow MA.
    """

    name = "ma_crossover"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self.fast_period = self.params.get("fast_period", 20)
        self.slow_period = self.params.get("slow_period", 50)

    def generate_signal(
        self,
        symbol: str,
        bars: pd.DataFrame,
        portfolio: PortfolioState | None = None,
    ) -> TradeSignal:
        if len(bars) < self.slow_period + 1:
            raise InsufficientDataError(
                f"Need at least {self.slow_period + 1} bars, got {len(bars)}"
            )

        close = bars["close"]
        fast_ma = close.rolling(window=self.fast_period).mean()
        slow_ma = close.rolling(window=self.slow_period).mean()

        return self._signal(
            symbol,
            current_fast=fast_ma.iloc[-1], current_slow=slow_ma.iloc[-1],
            prev_fast=fast_ma.iloc[-2], prev_slow=slow_ma.iloc[-2],
        )

    # ---- incremental backtest fast-path (R2 C-1b) ------------------------- #
    # The MAs are pure rolling means: the value at bar i depends only on the
    # window ending at i, so precomputing the full-series MAs once and indexing
    # row i is bit-identical to recomputing over close[:i+1] every bar.
    def supports_precompute(self) -> bool:
        return True

    def precompute(self, symbol: str, bars: pd.DataFrame) -> None:
        close = bars["close"]
        if not hasattr(self, "_ma_cache"):
            self._ma_cache: dict[str, tuple[pd.Series, pd.Series]] = {}
        self._ma_cache[symbol] = (
            close.rolling(window=self.fast_period).mean(),
            close.rolling(window=self.slow_period).mean(),
        )

    def generate_signal_at(
        self,
        symbol: str,
        bars: pd.DataFrame,
        i: int,
        portfolio: PortfolioState | None = None,
    ) -> TradeSignal:
        cached = getattr(self, "_ma_cache", {}).get(symbol)
        if cached is None:  # not precomputed → exact slice fallback
            return self.generate_signal(symbol, bars.iloc[: i + 1], portfolio)
        # len(bars[:i+1]) < slow+1  <=>  i < slow_period  → same guard as generate_signal
        if i < self.slow_period:
            raise InsufficientDataError(
                f"Need at least {self.slow_period + 1} bars, got {i + 1}"
            )
        fast_ma, slow_ma = cached
        return self._signal(
            symbol,
            current_fast=fast_ma.iloc[i], current_slow=slow_ma.iloc[i],
            prev_fast=fast_ma.iloc[i - 1], prev_slow=slow_ma.iloc[i - 1],
        )

    def _signal(self, symbol, *, current_fast, current_slow, prev_fast, prev_slow) -> TradeSignal:
        # Crossover detection
        if prev_fast <= prev_slow and current_fast > current_slow:
            signal = Signal.BUY
            spread = (current_fast - current_slow) / current_slow
            confidence = min(0.5 + spread * 10, 1.0)
        elif prev_fast >= prev_slow and current_fast < current_slow:
            signal = Signal.SELL
            spread = (current_slow - current_fast) / current_fast
            confidence = min(0.5 + spread * 10, 1.0)
        else:
            signal = Signal.HOLD
            confidence = 0.3

        logger.debug(
            f"{symbol} MA({self.fast_period}/{self.slow_period}): "
            f"fast={current_fast:.2f}, slow={current_slow:.2f} -> {signal.value}"
        )

        return self._make_signal(
            symbol=symbol,
            signal=signal,
            confidence=confidence,
            metadata={
                "fast_ma": current_fast,
                "slow_ma": current_slow,
                "fast_period": self.fast_period,
                "slow_period": self.slow_period,
            },
        )

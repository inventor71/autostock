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

        current_fast = fast_ma.iloc[-1]
        current_slow = slow_ma.iloc[-1]
        prev_fast = fast_ma.iloc[-2]
        prev_slow = slow_ma.iloc[-2]

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

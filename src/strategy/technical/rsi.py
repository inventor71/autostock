from __future__ import annotations

import pandas as pd
import ta
from loguru import logger

from src.core.exceptions import InsufficientDataError
from src.core.models import PortfolioState, TradeSignal
from src.core.types import Signal
from src.strategy.base import BaseStrategy
from src.strategy.registry import register_strategy


@register_strategy("rsi")
class RSIStrategy(BaseStrategy):
    """RSI (Relative Strength Index) strategy.

    BUY when RSI drops below oversold level (mean-reversion).
    SELL when RSI rises above overbought level.
    """

    name = "rsi"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self.period = self.params.get("period", 14)
        self.overbought = self.params.get("overbought", 70)
        self.oversold = self.params.get("oversold", 30)

    def generate_signal(
        self,
        symbol: str,
        bars: pd.DataFrame,
        portfolio: PortfolioState | None = None,
    ) -> TradeSignal:
        if len(bars) < self.period + 1:
            raise InsufficientDataError(
                f"Need at least {self.period + 1} bars, got {len(bars)}"
            )

        rsi = ta.momentum.RSIIndicator(bars["close"], window=self.period).rsi()
        current_rsi = rsi.iloc[-1]

        if current_rsi < self.oversold:
            signal = Signal.BUY
            # Stronger signal the more oversold
            confidence = min(0.5 + (self.oversold - current_rsi) / 30, 1.0)
        elif current_rsi > self.overbought:
            signal = Signal.SELL
            confidence = min(0.5 + (current_rsi - self.overbought) / 30, 1.0)
        else:
            signal = Signal.HOLD
            confidence = 0.3

        logger.debug(f"{symbol} RSI({self.period}): {current_rsi:.1f} -> {signal.value}")

        return self._make_signal(
            symbol=symbol,
            signal=signal,
            confidence=confidence,
            metadata={"rsi": current_rsi, "period": self.period},
        )

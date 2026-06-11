from __future__ import annotations

import pandas as pd
import ta
from loguru import logger

from src.core.exceptions import InsufficientDataError
from src.core.models import PortfolioState, TradeSignal
from src.core.types import Signal
from src.strategy.base import BaseStrategy
from src.strategy.registry import register_strategy


@register_strategy("macd")
class MACDStrategy(BaseStrategy):
    """MACD (Moving Average Convergence Divergence) strategy.

    BUY when MACD line crosses above signal line.
    SELL when MACD line crosses below signal line.
    """

    name = "macd"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self.fast_period = self.params.get("fast_period", 12)
        self.slow_period = self.params.get("slow_period", 26)
        self.signal_period = self.params.get("signal_period", 9)

    def generate_signal(
        self,
        symbol: str,
        bars: pd.DataFrame,
        portfolio: PortfolioState | None = None,
    ) -> TradeSignal:
        min_bars = self.slow_period + self.signal_period + 1
        if len(bars) < min_bars:
            raise InsufficientDataError(
                f"Need at least {min_bars} bars, got {len(bars)}"
            )

        macd_indicator = ta.trend.MACD(
            bars["close"],
            window_slow=self.slow_period,
            window_fast=self.fast_period,
            window_sign=self.signal_period,
        )

        macd_line = macd_indicator.macd()
        signal_line = macd_indicator.macd_signal()
        histogram = macd_indicator.macd_diff()

        current_hist = histogram.iloc[-1]
        prev_hist = histogram.iloc[-2]

        # Crossover: histogram changes sign
        if prev_hist <= 0 and current_hist > 0:
            signal = Signal.BUY
            confidence = min(0.5 + abs(current_hist) * 5, 1.0)
        elif prev_hist >= 0 and current_hist < 0:
            signal = Signal.SELL
            confidence = min(0.5 + abs(current_hist) * 5, 1.0)
        else:
            signal = Signal.HOLD
            confidence = 0.3

        logger.debug(
            f"{symbol} MACD: hist={current_hist:.4f}, "
            f"macd={macd_line.iloc[-1]:.4f} -> {signal.value}"
        )

        return self._make_signal(
            symbol=symbol,
            signal=signal,
            confidence=confidence,
            metadata={
                "macd": macd_line.iloc[-1],
                "signal_line": signal_line.iloc[-1],
                "histogram": current_hist,
            },
        )

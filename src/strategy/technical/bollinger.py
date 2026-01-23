from __future__ import annotations

import pandas as pd
import ta
from loguru import logger

from src.core.exceptions import InsufficientDataError
from src.core.models import PortfolioState, TradeSignal
from src.core.types import Signal
from src.strategy.base import BaseStrategy
from src.strategy.registry import register_strategy


@register_strategy("bollinger")
class BollingerBandsStrategy(BaseStrategy):
    """Bollinger Bands mean-reversion strategy.

    BUY when price touches or crosses below lower band (oversold).
    SELL when price touches or crosses above upper band (overbought).
    """

    name = "bollinger"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self.period = self.params.get("period", 20)
        self.num_std = self.params.get("num_std", 2.0)

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

        bb = ta.volatility.BollingerBands(
            bars["close"],
            window=self.period,
            window_dev=self.num_std,
        )

        upper = bb.bollinger_hband().iloc[-1]
        lower = bb.bollinger_lband().iloc[-1]
        middle = bb.bollinger_mavg().iloc[-1]
        current_price = bars["close"].iloc[-1]

        # %B indicator: position within bands
        band_width = upper - lower
        if band_width > 0:
            pct_b = (current_price - lower) / band_width
        else:
            pct_b = 0.5

        if current_price <= lower:
            signal = Signal.BUY
            confidence = min(0.5 + (1 - pct_b) * 0.5, 1.0)
        elif current_price >= upper:
            signal = Signal.SELL
            confidence = min(0.5 + (pct_b - 1) * 0.5, 1.0)
        else:
            signal = Signal.HOLD
            confidence = 0.3

        logger.debug(
            f"{symbol} BB({self.period}, {self.num_std}): "
            f"price={current_price:.2f}, %B={pct_b:.2f} -> {signal.value}"
        )

        return self._make_signal(
            symbol=symbol,
            signal=signal,
            confidence=confidence,
            metadata={
                "upper_band": upper,
                "lower_band": lower,
                "middle_band": middle,
                "pct_b": pct_b,
            },
        )

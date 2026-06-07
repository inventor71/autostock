from __future__ import annotations

import pandas as pd
from loguru import logger

from src.core.exceptions import InsufficientDataError
from src.core.models import PortfolioState, TradeSignal
from src.core.types import Signal
from src.strategy.base import BaseStrategy
from src.strategy.registry import register_strategy


@register_strategy("buy_and_hold")
class BuyAndHoldStrategy(BaseStrategy):
    """The simplest benchmark: equal-weight buy the universe, then hold.

    BUY any symbol not yet held; HOLD once a position exists. Driven over the
    engine's per-symbol loop this becomes "buy each universe symbol once, then
    sit" — the floor every active strategy must beat to justify its cost.
    """

    name = "buy_and_hold"

    def generate_signal(
        self,
        symbol: str,
        bars: pd.DataFrame,
        portfolio: PortfolioState | None = None,
    ) -> TradeSignal:
        if bars is None or len(bars) == 0:
            raise InsufficientDataError(f"Need at least 1 bar for {symbol}, got 0")

        held = portfolio is not None and symbol in portfolio.positions
        if held:
            signal = Signal.HOLD
            confidence = 0.0
        else:
            signal = Signal.BUY
            confidence = 1.0

        logger.debug(f"{symbol} buy_and_hold: held={held} -> {signal.value}")

        return self._make_signal(symbol=symbol, signal=signal, confidence=confidence)

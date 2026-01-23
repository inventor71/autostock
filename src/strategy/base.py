from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from src.core.models import PortfolioState, TradeSignal
from src.core.types import Signal


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    name: str = "base"

    def __init__(self, params: dict | None = None):
        self.params = params or {}

    @abstractmethod
    def generate_signal(
        self,
        symbol: str,
        bars: pd.DataFrame,
        portfolio: PortfolioState | None = None,
    ) -> TradeSignal:
        """Generate a trading signal from market data.

        Args:
            symbol: The ticker symbol.
            bars: DataFrame with columns [open, high, low, close, volume].
            portfolio: Current portfolio state (optional).

        Returns:
            TradeSignal with signal direction and confidence.
        """
        pass

    def _make_signal(
        self,
        symbol: str,
        signal: Signal,
        confidence: float = 0.5,
        metadata: dict | None = None,
    ) -> TradeSignal:
        return TradeSignal(
            symbol=symbol,
            signal=signal,
            confidence=confidence,
            strategy_name=self.name,
            metadata=metadata or {},
        )

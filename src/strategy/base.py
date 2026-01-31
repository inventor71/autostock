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

    def supports_selection(self) -> bool:
        """Return whether this strategy supports dynamic symbol selection.

        Strategies that return True should implement select_symbols() to
        dynamically choose which symbols to trade from the universe.

        Returns:
            False by default (trades all symbols in universe).
        """
        return False

    def select_symbols(
        self,
        universe: list[str],
        market_data: dict[str, pd.DataFrame],
        portfolio: PortfolioState | None = None,
    ) -> list[str]:
        """Select symbols to trade from the universe.

        Override this method in subclasses to implement custom symbol
        selection logic (e.g., momentum screening, sector rotation).

        Args:
            universe: List of available symbols to choose from.
            market_data: Dict mapping symbol to its OHLCV DataFrame.
            portfolio: Current portfolio state (optional).

        Returns:
            List of symbols to trade (default: entire universe).
        """
        return universe

    def _make_signal(
        self,
        symbol: str,
        signal: Signal,
        confidence: float = 0.5,
        sell_pct: float = 1.0,
        metadata: dict | None = None,
    ) -> TradeSignal:
        return TradeSignal(
            symbol=symbol,
            signal=signal,
            confidence=confidence,
            sell_pct=sell_pct,
            strategy_name=self.name,
            metadata=metadata or {},
        )

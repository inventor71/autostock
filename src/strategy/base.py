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

    def supports_precompute(self) -> bool:
        """Return whether this strategy supports an incremental backtest fast-path.

        A strategy whose indicators are causal/rolling (value at bar *i* depends
        only on data ``[0:i]``) can compute its full-series state ONCE via
        ``precompute()`` and answer each bar in O(1) via ``generate_signal_at()``,
        instead of recomputing over a growing slice every bar (the O(n^2) default).

        False by default → the engine uses the slice + ``generate_signal`` path,
        so existing strategies behave exactly as before.
        """
        return False

    def precompute(self, symbol: str, bars: pd.DataFrame) -> None:
        """Optional hook: precompute full-series indicator state for ``symbol``.

        Called once per symbol before the bar loop when ``supports_precompute()``
        is True. Default is a no-op.
        """
        return None

    def generate_signal_at(
        self,
        symbol: str,
        bars: pd.DataFrame,
        i: int,
        portfolio: PortfolioState | None = None,
    ) -> TradeSignal:
        """Signal for bar ``i`` over the full ``bars`` frame.

        Default delegates to ``generate_signal(bars[:i+1])`` — i.e. identical
        behavior with no speedup. A strategy overriding this for the fast-path
        MUST return exactly what the default would (the backtest characterization
        golden enforces this).
        """
        return self.generate_signal(symbol, bars.iloc[: i + 1], portfolio)

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

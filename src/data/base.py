from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

import pandas as pd

from src.core.types import TimeFrame


class BaseDataProvider(ABC):
    """Abstract base class for all data providers."""

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        timeframe: TimeFrame = TimeFrame.DAY_1,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        """Fetch OHLCV bars for a symbol.

        Returns DataFrame with columns: open, high, low, close, volume
        Index should be DatetimeIndex.
        """
        pass

    @abstractmethod
    def get_latest_price(self, symbol: str) -> float:
        """Get the latest price for a symbol."""
        pass

    def get_multiple_bars(
        self,
        symbols: list[str],
        timeframe: TimeFrame = TimeFrame.DAY_1,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> dict[str, pd.DataFrame]:
        """Fetch bars for multiple symbols."""
        return {
            symbol: self.get_bars(symbol, timeframe, start, end, limit)
            for symbol in symbols
        }

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime

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

    def get_daily_bar(self, symbol: str, d: date) -> dict | None:
        """Return a single trading day's OHLCV + prev_close as a dict.

        Returns ``None`` when data is unavailable (holiday, error, …).
        Default implementation delegates to ``get_bars`` with Day timeframe.
        """
        start = datetime(d.year, d.month, d.day)
        end = start + pd.Timedelta(days=1)
        df = self.get_bars(symbol, TimeFrame.DAY_1, start=start, end=end, limit=2)
        if df.empty:
            return None
        row = df.iloc[-1]
        prev_close: float | None = None
        if len(df) >= 2:
            prev_close = float(df.iloc[-2]["close"])
        return {
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row.get("volume", 0)),
            "prev_close": prev_close,
        }

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

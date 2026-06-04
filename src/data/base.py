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
        symbol: str | list[str],
        timeframe: TimeFrame = TimeFrame.DAY_1,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> pd.DataFrame | dict[str, pd.DataFrame]:
        """Fetch OHLCV bars for one or more symbols.

        Returns:
            - ``pd.DataFrame`` when ``symbol`` is a single str (columns: open, high, low, close, volume;
              DatetimeIndex).
            - ``dict[str, pd.DataFrame]`` when ``symbol`` is a list of str.
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

        The lookback starts a week before ``d`` (not the same day) so the result
        includes the **previous trading day's** bar — otherwise ``prev_close``
        could never be resolved across weekends/holidays.
        """
        start = datetime(d.year, d.month, d.day) - pd.Timedelta(days=7)
        end = datetime(d.year, d.month, d.day) + pd.Timedelta(days=1)
        df = self.get_bars(symbol, TimeFrame.DAY_1, start=start, end=end, limit=10)
        if df.empty:
            return None

        # Locate the row for ``d`` ("today"); fall back to the latest available
        # bar when ``d`` itself is missing (e.g. holiday / not-yet-printed).
        today_pos = len(df) - 1
        for i in range(len(df) - 1, -1, -1):
            idx = df.index[i]
            idx_date = idx.date() if hasattr(idx, "date") else idx
            if idx_date == d:
                today_pos = i
                break

        row = df.iloc[today_pos]
        prev_close: float | None = None
        if today_pos >= 1:
            prev_close = float(df.iloc[today_pos - 1]["close"])
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

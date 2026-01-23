from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf
from loguru import logger

from src.core.exceptions import DataProviderError
from src.core.types import TimeFrame
from src.data.base import BaseDataProvider


TIMEFRAME_MAP = {
    TimeFrame.MINUTE_1: "1m",
    TimeFrame.MINUTE_5: "5m",
    TimeFrame.MINUTE_15: "15m",
    TimeFrame.MINUTE_30: "30m",
    TimeFrame.HOUR_1: "1h",
    TimeFrame.HOUR_4: "4h",  # Not directly supported, will use 1h
    TimeFrame.DAY_1: "1d",
    TimeFrame.WEEK_1: "1wk",
    TimeFrame.MONTH_1: "1mo",
}


class YFinanceProvider(BaseDataProvider):
    """Data provider using yfinance for historical OHLCV data."""

    def get_bars(
        self,
        symbol: str,
        timeframe: TimeFrame = TimeFrame.DAY_1,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        try:
            ticker = yf.Ticker(symbol)
            yf_interval = TIMEFRAME_MAP.get(timeframe, "1d")

            if start and end:
                df = ticker.history(
                    start=start.strftime("%Y-%m-%d"),
                    end=end.strftime("%Y-%m-%d"),
                    interval=yf_interval,
                )
            else:
                period = self._limit_to_period(limit, timeframe)
                df = ticker.history(period=period, interval=yf_interval)

            if df.empty:
                raise DataProviderError(f"No data returned for {symbol}")

            df.columns = [c.lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]]
            df.index.name = "timestamp"

            logger.debug(f"Fetched {len(df)} bars for {symbol} ({timeframe.value})")
            return df

        except DataProviderError:
            raise
        except Exception as e:
            raise DataProviderError(f"Failed to fetch data for {symbol}: {e}") from e

    def get_latest_price(self, symbol: str) -> float:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            return float(info.last_price)
        except Exception as e:
            raise DataProviderError(f"Failed to get price for {symbol}: {e}") from e

    @staticmethod
    def _limit_to_period(limit: int, timeframe: TimeFrame) -> str:
        if timeframe in (TimeFrame.MINUTE_1, TimeFrame.MINUTE_5):
            days = max(1, limit // 78)  # ~78 bars per trading day for 5m
            return f"{min(days, 59)}d"
        elif timeframe in (TimeFrame.MINUTE_15, TimeFrame.MINUTE_30):
            days = max(1, limit // 26)
            return f"{min(days, 59)}d"
        elif timeframe in (TimeFrame.HOUR_1, TimeFrame.HOUR_4):
            days = max(1, limit // 7)
            return f"{min(days, 729)}d"
        elif timeframe == TimeFrame.DAY_1:
            days = max(1, int(limit * 1.5))  # Account for weekends
            return f"{min(days, 7300)}d"
        elif timeframe == TimeFrame.WEEK_1:
            return f"{min(limit * 7, 7300)}d"
        else:
            return "max"

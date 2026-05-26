from __future__ import annotations

import warnings
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore", message="Timestamp.utcnow is deprecated")
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
        """Translate a desired bar count into a yfinance `period` string.

        yfinance fetches by calendar period, not bar count, so we estimate how
        many calendar days are needed to yield ~`limit` bars of the requested
        timeframe, then pad to absorb weekends, holidays and partial sessions.

        yfinance intraday history is capped: 1m only goes back ~7 days and
        other intraday intervals (5m/15m/30m/1h) ~60 days. Hourly bars can
        reach ~730 days. Those caps are enforced here. For a 5-minute batch
        interval over ~13 regular-hours bars/day, `limit=100` resolves to a few
        days of bars — comfortably above the ~50 bars the LLM strategy needs.
        """
        # ~78 five-minute bars and ~26 fifteen/thirty-minute bars per regular
        # 6.5h session. Estimate the calendar days needed, then add 1.4x slack
        # plus a couple of days so partial/holiday sessions can't starve a
        # strategy that needs ~50 bars.
        def _pad_days(bars_per_day: int) -> int:
            sessions = max(1, limit / bars_per_day)
            return int(sessions * 1.4) + 2

        if timeframe == TimeFrame.MINUTE_1:
            days = _pad_days(390)  # 390 one-minute bars per session
            return f"{min(days, 7)}d"  # yfinance: 1m only ~7 days back
        elif timeframe == TimeFrame.MINUTE_5:
            days = _pad_days(78)
            return f"{min(days, 59)}d"
        elif timeframe in (TimeFrame.MINUTE_15, TimeFrame.MINUTE_30):
            days = _pad_days(26)
            return f"{min(days, 59)}d"
        elif timeframe in (TimeFrame.HOUR_1, TimeFrame.HOUR_4):
            days = _pad_days(7)
            return f"{min(days, 729)}d"
        elif timeframe == TimeFrame.DAY_1:
            days = max(1, int(limit * 1.5))  # Account for weekends
            return f"{min(days, 7300)}d"
        elif timeframe == TimeFrame.WEEK_1:
            return f"{min(limit * 7, 7300)}d"
        else:
            return "max"

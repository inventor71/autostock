from __future__ import annotations

from datetime import datetime

import pandas as pd
from loguru import logger

from src.core.exceptions import DataProviderError
from src.core.types import TimeFrame
from src.data.base import BaseDataProvider

try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame as AlpacaTimeFrame, TimeFrameUnit
except ImportError:
    StockHistoricalDataClient = None


TIMEFRAME_MAP = {
    TimeFrame.MINUTE_1: (1, "Minute"),
    TimeFrame.MINUTE_5: (5, "Minute"),
    TimeFrame.MINUTE_15: (15, "Minute"),
    TimeFrame.MINUTE_30: (30, "Minute"),
    TimeFrame.HOUR_1: (1, "Hour"),
    TimeFrame.HOUR_4: (4, "Hour"),
    TimeFrame.DAY_1: (1, "Day"),
    TimeFrame.WEEK_1: (1, "Week"),
    TimeFrame.MONTH_1: (1, "Month"),
}


class AlpacaDataProvider(BaseDataProvider):
    """Data provider using Alpaca API for real-time and historical data."""

    def __init__(self, api_key: str, secret_key: str):
        if StockHistoricalDataClient is None:
            raise DataProviderError("alpaca-py not installed")
        self._client = StockHistoricalDataClient(api_key, secret_key)

    def get_bars(
        self,
        symbol: str,
        timeframe: TimeFrame = TimeFrame.DAY_1,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        try:
            amount, unit = TIMEFRAME_MAP[timeframe]
            alpaca_tf = AlpacaTimeFrame(amount, TimeFrameUnit[unit])

            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=alpaca_tf,
                start=start,
                end=end,
                limit=limit,
            )

            bars = self._client.get_stock_bars(request)
            df = bars.df

            if df.empty:
                raise DataProviderError(f"No data returned for {symbol}")

            # Flatten multi-index if present
            if isinstance(df.index, pd.MultiIndex):
                df = df.droplevel("symbol")

            df.columns = [c.lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]]
            df.index.name = "timestamp"

            logger.debug(f"Fetched {len(df)} bars for {symbol} from Alpaca")
            return df

        except DataProviderError:
            raise
        except Exception as e:
            raise DataProviderError(f"Alpaca data error for {symbol}: {e}") from e

    def get_latest_price(self, symbol: str) -> float:
        try:
            from alpaca.data.requests import StockLatestBarRequest

            request = StockLatestBarRequest(symbol_or_symbols=symbol)
            bar = self._client.get_stock_latest_bar(request)
            return float(bar[symbol].close)
        except Exception as e:
            raise DataProviderError(f"Failed to get price for {symbol}: {e}") from e

"""Toss OHLCV normalized to bar-start timestamps and completed bars only."""
from __future__ import annotations

import re
from datetime import date, datetime

import pandas as pd

from src.core.exceptions import DataProviderError
from src.core.types import TimeFrame
from src.data.base import BaseDataProvider
from src.execution.brokers.toss.client import TossClient

_COLUMNS = ["open", "high", "low", "close", "volume"]
_MINUTES = {
    TimeFrame.MINUTE_1: 1, TimeFrame.MINUTE_5: 5, TimeFrame.MINUTE_15: 15,
    TimeFrame.MINUTE_30: 30, TimeFrame.HOUR_1: 60, TimeFrame.HOUR_4: 240,
}


class TossDataProvider(BaseDataProvider):
    def __init__(self, client: TossClient, *, market: str = "US", adjusted: bool = True):
        if market not in {"US", "KR"}:
            raise ValueError("Toss data market must be US or KR")
        self.client = client
        self.market = market
        self.currency = "USD" if market == "US" else "KRW"
        self.timezone = "America/New_York" if market == "US" else "Asia/Seoul"
        self.adjusted = adjusted

    def _timestamp(self, value) -> pd.Timestamp:
        stamp = pd.Timestamp(value)
        return stamp.tz_localize(self.timezone) if stamp.tzinfo is None else stamp.tz_convert(self.timezone)

    @staticmethod
    def _symbol(symbol: str) -> str:
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z0-9.\-]{1,20}", symbol):
            raise DataProviderError("Invalid Toss symbol")
        return symbol.upper()

    def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        names = list(dict.fromkeys(self._symbol(symbol) for symbol in symbols))
        prices = {}
        for offset in range(0, len(names), 200):
            rows = self.client.request(
                "GET", "/api/v1/prices", params={"symbols": ",".join(names[offset:offset + 200])},
            )
            for row in rows:
                if row["currency"] != self.currency:
                    raise DataProviderError("Toss quote currency does not match the selected market")
                price = float(row["lastPrice"])
                if not 0 < price < float("inf"):
                    raise DataProviderError("Toss returned an invalid price")
                prices[row["symbol"]] = price
        return prices

    def get_latest_price(self, symbol: str) -> float:
        name = self._symbol(symbol)
        prices = self.get_latest_prices([name])
        if name not in prices:
            raise DataProviderError("Toss did not return the requested quote")
        return prices[name]

    def get_latest_quote(self, symbol: str) -> dict:
        name = self._symbol(symbol)
        rows = self.client.request("GET", "/api/v1/prices", params={"symbols": name})
        for row in rows:
            if row.get("symbol") != name:
                continue
            if row.get("currency") != self.currency:
                raise DataProviderError("Toss quote currency does not match the selected market")
            price = float(row["lastPrice"])
            if not 0 < price < float("inf"):
                raise DataProviderError("Toss returned an invalid price")
            return {"price": price, "source_as_of": row.get("timestamp"), "currency": self.currency}
        raise DataProviderError("Toss did not return the requested quote")

    def get_bars(
        self, symbol: str | list[str], timeframe: TimeFrame = TimeFrame.DAY_1,
        start: datetime | None = None, end: datetime | None = None, limit: int = 100,
    ) -> pd.DataFrame | dict[str, pd.DataFrame]:
        if isinstance(symbol, list):
            return {name: self.get_bars(name, timeframe, start, end, limit) for name in symbol}
        symbol = self._symbol(symbol)
        if timeframe not in _MINUTES and timeframe != TimeFrame.DAY_1:
            raise DataProviderError("Toss adapter supports 1m through 4h and daily bars")
        if not isinstance(limit, int) or not 1 <= limit <= 100_000:
            raise DataProviderError("Toss bar limit must be between 1 and 100000")
        now = pd.Timestamp.now(tz=self.timezone)
        cutoff = min(self._timestamp(end), now) if end else now
        lower = self._timestamp(start) if start else None
        if lower is not None and lower >= cutoff:
            return self._empty()
        minutes = _MINUTES.get(timeframe, 1)
        params = {
            "symbol": symbol, "interval": "1d" if timeframe == TimeFrame.DAY_1 else "1m",
            "count": 200, "before": cutoff.isoformat(), "adjusted": str(self.adjusted).lower(),
        }
        rows, cursors = {}, set()
        result = self._empty()
        for _ in range(1000):
            page = self.client.request("GET", "/api/v1/candles", params=params)
            candles = page["candles"]
            for candle in candles:
                if candle["currency"] != self.currency:
                    raise DataProviderError("Toss candle currency does not match the selected market")
                stamp = self._timestamp(candle["timestamp"])
                # API minute timestamps denote the END of [t-1m, t), whereas
                # Autostock/Alpaca consumers index by the START of the candle.
                if timeframe == TimeFrame.DAY_1:
                    stamp = stamp.normalize()
                    # US daily OHLC is regular-session only. KR's combined bars
                    # may change until 20:00; wait until that session ends.
                    complete = stamp + pd.Timedelta(hours=16 if self.market == "US" else 20)
                else:
                    complete = stamp
                    stamp -= pd.Timedelta(minutes=1)
                if complete > cutoff or (lower is not None and stamp < lower):
                    continue
                values = [float(candle[k]) for k in (
                    "openPrice", "highPrice", "lowPrice", "closePrice", "volume",
                )]
                if any(not 0 <= v < float("inf") for v in values) or min(values[:4]) <= 0:
                    raise DataProviderError("Toss returned invalid OHLCV")
                rows.setdefault(stamp, values)  # inclusive before can repeat a boundary candle
            if rows:
                result = pd.DataFrame.from_dict(rows, orient="index", columns=_COLUMNS).sort_index()
                result.index = pd.DatetimeIndex(result.index, name="timestamp")
                if minutes > 1:
                    result = result.resample(
                        f"{minutes}min", closed="left", label="left", origin="start_day",
                        offset="9h30min" if self.market == "US" else "9h",
                    ).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
                    result = result.dropna(subset=_COLUMNS[:4])
                    # Exclude unfinished buckets and a first bucket whose start
                    # precedes the data fetched so far (do not fabricate its open).
                    result = result[(result.index + pd.Timedelta(minutes=minutes) <= cutoff)
                                    & (result.index >= min(rows))]
                if len(result) >= limit:
                    return result.tail(limit)
            if not candles or not page.get("nextBefore"):
                return result.tail(limit)
            oldest = min(self._timestamp(c["timestamp"]) for c in candles)
            if lower is not None and oldest <= lower:
                return result.tail(limit)
            cursor = page["nextBefore"]
            if cursor in cursors:
                raise DataProviderError("Toss candle pagination did not advance")
            cursors.add(cursor)
            params["before"] = cursor
        raise DataProviderError("Toss candle pagination exceeded the bound")

    def _empty(self) -> pd.DataFrame:
        return pd.DataFrame(columns=_COLUMNS, index=pd.DatetimeIndex([], tz=self.timezone, name="timestamp"))

    def get_daily_bar(self, symbol: str, d: date) -> dict | None:
        # BaseDataProvider falls back to an earlier day when d is absent. That
        # would mislabel an incomplete/future Toss daily candle as today's data.
        start = datetime(d.year, d.month, d.day) - pd.Timedelta(days=10)
        end = datetime(d.year, d.month, d.day) + pd.Timedelta(days=1)
        frame = self.get_bars(symbol, start=start, end=end, limit=15)
        matching = [i for i, stamp in enumerate(frame.index) if stamp.date() == d]
        if not matching:
            return None
        index = matching[-1]
        result = {k: float(frame.iloc[index][k]) for k in _COLUMNS}
        result["prev_close"] = float(frame.iloc[index - 1]["close"]) if index else None
        return result

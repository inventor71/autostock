"""Bar/price cache + pure indicators (critic#7).

The 5s wake detector must never do a synchronous market-data fetch on the
scheduler thread (a slow call would overrun the interval and ``coalesce`` would
silently drop ticks). So bar/price fetches go through ``BarCache`` (TTL-gated,
best-effort, returns the last cached value on failure), and the abnormal-move
math (``atr``/``avg_volume``) is pure and PBT-tested separately.
"""

from __future__ import annotations

import time

import pandas as pd
from loguru import logger

from src.core.types import TimeFrame


def atr(bars: pd.DataFrame | None, period: int = 14) -> float | None:
    """Average True Range over the last ``period`` bars (pure). None if insufficient."""
    if bars is None or len(bars) < 2:
        return None
    high, low, close = bars["high"], bars["low"], bars["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1).dropna()
    if len(tr) == 0:
        return None
    return float(tr.tail(period).mean())


def avg_volume(bars: pd.DataFrame | None, period: int = 20) -> float | None:
    """Mean volume over the last ``period`` bars (pure). None if unavailable."""
    if bars is None or "volume" not in getattr(bars, "columns", []) or len(bars) == 0:
        return None
    return float(bars["volume"].tail(period).mean())


class BarCache:
    """Per-symbol TTL cache over a data provider; best-effort, never raises."""

    def __init__(self, data_provider, *, bars_ttl: float = 60.0, price_ttl: float = 3.0,
                 timeframe: TimeFrame = TimeFrame.MINUTE_5, limit: int = 50):
        self._dp = data_provider
        self._bars_ttl = bars_ttl
        self._price_ttl = price_ttl
        self._timeframe = timeframe
        self._limit = limit
        self._bars: dict[str, tuple[float, pd.DataFrame]] = {}
        self._price: dict[str, tuple[float, float]] = {}

    def get_bars(self, symbol: str) -> pd.DataFrame | None:
        now = time.monotonic()
        hit = self._bars.get(symbol)
        if hit and now - hit[0] < self._bars_ttl:
            return hit[1]
        try:
            bars = self._dp.get_bars(symbol, timeframe=self._timeframe, limit=self._limit)
        except Exception as e:
            logger.warning("bars fetch failed for {} (using cached): {}", symbol, e)
            return hit[1] if hit else None
        self._bars[symbol] = (now, bars)
        return bars

    def get_price(self, symbol: str) -> float | None:
        now = time.monotonic()
        hit = self._price.get(symbol)
        if hit and now - hit[0] < self._price_ttl:
            return hit[1]
        try:
            price = float(self._dp.get_latest_price(symbol))
        except Exception as e:
            logger.warning("price fetch failed for {} (using cached): {}", symbol, e)
            return hit[1] if hit else None
        self._price[symbol] = (now, price)
        return price

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
    """Mean volume over the ``period`` bars BEFORE the last one (pure).

    Excludes the current/last bar so a volume spike doesn't inflate its own
    baseline and mask itself (review #6). None if there's no prior bar."""
    if bars is None or "volume" not in getattr(bars, "columns", []) or len(bars) < 2:
        return None
    return float(bars["volume"].iloc[:-1].tail(period).mean())


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

    # ---- F14: cache-only reads (NEVER fetch) + a prefetch worker ---------- #
    # The 5s WakeDetector tick MUST NOT do a synchronous market-data fetch on the
    # scheduler thread (a stalled/half-open socket would overrun the interval and
    # wedge the daemon — the very bug F14 fixes). So detect_wakes reads via peek_*
    # (last cached value or None, TTL ignored) and a separate ``prefetch`` job
    # (its own scheduler thread) keeps the cache warm via the fetching get_*.
    def peek_price(self, symbol: str) -> float | None:
        """Last cached price (None if never fetched). NEVER fetches."""
        hit = self._price.get(symbol)
        return hit[1] if hit else None

    def peek_bars(self, symbol: str) -> pd.DataFrame | None:
        """Last cached bars (None if never fetched). NEVER fetches."""
        hit = self._bars.get(symbol)
        return hit[1] if hit else None

    def prefetch(self, symbols) -> None:
        """Warm the price (every call) + bars (bars_ttl-gated) caches for ``symbols``.

        Runs on its OWN scheduler job (off the detect thread). Each get_* is
        best-effort and now bounded by the broker/provider HTTP timeout (F14-A),
        so a slow symbol can't hang the worker. De-dupes symbols defensively."""
        for sym in dict.fromkeys(s for s in symbols if s):
            self.get_price(sym)
            self.get_bars(sym)

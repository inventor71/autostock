"""Per-symbol circular buffer for early-session bar data.

Retains the last *retention_minutes* of 1-min OHLCV bars per symbol in a
``collections.deque``. Single-threaded by design (APScheduler job thread).
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from src.early_session.records import BarRecord


class BufferManager:
    """In-memory circular buffer keyed by symbol.

    Thread-safety: single-threaded access only (P2 — APScheduler job thread).
    """

    def __init__(self, retention_minutes: int = 20):
        self._retention_minutes = retention_minutes
        self._buffer: dict[str, deque[BarRecord]] = {}

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def push(self, symbol: str, bar: BarRecord) -> None:
        """Append a bar and evict bars older than *retention_minutes*."""
        if symbol not in self._buffer:
            self._buffer[symbol] = deque()
        self._buffer[symbol].append(bar)
        self._trim(symbol, bar.timestamp)

    def get_window(self, symbol: str, minutes: int) -> list[BarRecord]:
        """Return bars from the last *minutes* minutes (inclusive)."""
        deq = self._buffer.get(symbol)
        if not deq:
            return []
        cutoff = deq[-1].timestamp - timedelta(minutes=minutes)
        return [b for b in deq if b.timestamp >= cutoff]

    def get_range(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[BarRecord]:
        """Return bars whose timestamp falls in [*start*, *end*]."""
        deq = self._buffer.get(symbol)
        if not deq:
            return []
        return [b for b in deq if start <= b.timestamp <= end]

    def clear(self, symbol: str) -> None:
        """Drop all buffered bars for *symbol*."""
        self._buffer.pop(symbol, None)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _trim(self, symbol: str, now: datetime) -> None:
        """Remove bars older than *retention_minutes* from the front."""
        cutoff = now - timedelta(minutes=self._retention_minutes)
        deq = self._buffer.get(symbol)
        if deq is None:
            return
        while deq and deq[0].timestamp < cutoff:
            deq.popleft()

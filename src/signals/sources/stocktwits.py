"""StockTwits symbol-stream source (F77).

Reads a symbol's recent messages from the UNAUTHENTICATED public stream and
aggregates only the author self-declared labels (``entities.sentiment.basic``:
Bullish/Bearish). Message bodies and usernames are never returned or stored
(SECURITY-03 / NFR-4) — the labels are the whole signal.

This endpoint is not a contracted partner API: it can change shape or start
rejecting us at any time. Transport/HTTP errors raise so the caller (the sweep
runner) can degrade; a 429/403 raises :class:`RateLimited` so the sweep aborts
the whole tick instead of hammering on (NFR-3).
"""

from __future__ import annotations

from datetime import datetime

from src.signals.records import SentimentRecord

_BASE_URL = "https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"

# StockTwits 403s the default python-requests User-Agent (bot filter) while
# serving the same unauthenticated endpoint to browsers — send a plain desktop
# UA. If they tighten further, every call degrades fail-honest (RateLimited).
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}


class RateLimited(Exception):
    """StockTwits answered 429/403 — stop the sweep, retry next tick."""


def _norm(symbol: str) -> str:
    return symbol.strip().upper()


class StocktwitsSource:
    """Fetch one symbol's label aggregate (one HTTP call per symbol)."""

    def __init__(
        self,
        *,
        http_connect_timeout: float = 3.0,
        http_read_timeout: float = 5.0,
    ):
        self._timeout = (http_connect_timeout, http_read_timeout)

    def fetch_symbol(self, symbol: str, *, ts: datetime | None = None) -> SentimentRecord:
        """Aggregate the symbol stream's recent messages into a SentimentRecord.

        Raises ``RateLimited`` on 429/403; any other transport/HTTP/shape error
        raises normally (caller skips the symbol).
        """
        import requests

        symbol = _norm(symbol)
        resp = requests.get(_BASE_URL.format(symbol=symbol),
                            headers=_HEADERS, timeout=self._timeout)
        if resp.status_code in (403, 429):
            raise RateLimited(f"stocktwits {resp.status_code} for {symbol}")
        resp.raise_for_status()
        payload = resp.json() or {}

        bullish = bearish = untagged = 0
        latest_id: int | None = None
        for msg in payload.get("messages", []) or []:
            if not isinstance(msg, dict):
                continue  # unexpected shape — skip the message (SECURITY-05)
            mid = msg.get("id")
            if isinstance(mid, int):
                latest_id = mid if latest_id is None else max(latest_id, mid)
            label = (((msg.get("entities") or {}).get("sentiment") or {}) or {}).get("basic")
            if label == "Bullish":
                bullish += 1
            elif label == "Bearish":
                bearish += 1
            else:
                untagged += 1

        return SentimentRecord(
            ts=ts or datetime.now().astimezone(),
            symbol=symbol,
            bullish_n=bullish,
            bearish_n=bearish,
            untagged_n=untagged,
            latest_id=latest_id,
        )

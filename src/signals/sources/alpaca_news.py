"""Alpaca News (Benzinga-powered) provider (F61, FR-2).

Real-time + historical headlines, an upgrade over the yfinance feed for catalyst
detection. Returns the same ``NewsItem`` shape as ``YFinanceNewsProvider`` so the
collector and the existing ``news`` tool can use either interchangeably.

Best-effort: a failure raises (the caller degrades / falls back). Timeout-bounded
via the shared F14 session-timeout helper so a half-open socket can't wedge the
scheduler.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger

from src.data.providers.news_provider import NewsItem
from src.execution.brokers.session_timeout import install_session_timeout


class AlpacaNewsProvider:
    """News via alpaca-py ``NewsClient``. Benzinga gives no sentiment on the
    free tier, so ``sentiment_score`` is left ``None`` (fail-honest — no fake
    number)."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        *,
        http_connect_timeout: float = 3.0,
        http_read_timeout: float = 5.0,
        cache_ttl_minutes: float = 15.0,
    ):
        from alpaca.data.historical.news import NewsClient

        self._client = NewsClient(api_key, secret_key)
        install_session_timeout(
            self._client, connect=http_connect_timeout, read=http_read_timeout
        )
        self._cache: dict[str, tuple[datetime, list[NewsItem]]] = {}
        self._cache_ttl_minutes = cache_ttl_minutes

    def get_news(self, symbol: str, limit: int = 8) -> list[NewsItem]:
        """Recent headlines for ``symbol``, newest first."""
        sym = symbol.upper()
        if sym in self._cache:
            cached_at, cached = self._cache[sym]
            if (datetime.now() - cached_at).total_seconds() / 60 < self._cache_ttl_minutes:
                return cached[:limit]

        from alpaca.data.requests import NewsRequest

        request = NewsRequest(symbols=sym, limit=limit, sort="desc", exclude_contentless=True)
        news_set = self._client.get_news(request)
        articles = news_set.data.get("news", []) if hasattr(news_set, "data") else []

        items: list[NewsItem] = []
        for art in articles[:limit]:
            items.append(
                NewsItem(
                    title=getattr(art, "headline", "") or "",
                    summary=getattr(art, "summary", "") or "",
                    link=getattr(art, "url", "") or "",
                    publisher=getattr(art, "source", "") or "",
                    published_at=getattr(art, "updated_at", None)
                    or getattr(art, "created_at", None),
                    sentiment_score=None,
                )
            )

        self._cache[sym] = (datetime.now(), items)
        logger.debug("Alpaca news: {} items for {}", len(items), sym)
        return items

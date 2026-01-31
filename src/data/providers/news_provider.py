"""News data provider using yfinance."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import yfinance as yf
from loguru import logger
from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    """A news article item."""

    title: str
    summary: str = ""
    link: str = ""
    publisher: str = ""
    published_at: datetime | None = None
    sentiment_score: float | None = None  # -1 to 1, negative to positive

    model_config = {"arbitrary_types_allowed": True}


class YFinanceNewsProvider:
    """News provider using yfinance Ticker.news.

    Fetches recent news headlines for a given symbol
    using the yfinance library.
    """

    def __init__(self):
        self._cache: dict[str, tuple[datetime, list[NewsItem]]] = {}
        self._cache_ttl_minutes = 15

    def get_news(self, symbol: str, limit: int = 10) -> list[NewsItem]:
        """Get recent news for a symbol.

        Args:
            symbol: Ticker symbol (e.g., "AAPL").
            limit: Maximum number of news items to return.

        Returns:
            List of NewsItem objects, newest first.
        """
        # Check cache
        if symbol in self._cache:
            cached_time, cached_news = self._cache[symbol]
            age_minutes = (datetime.now() - cached_time).total_seconds() / 60
            if age_minutes < self._cache_ttl_minutes:
                return cached_news[:limit]

        try:
            ticker = yf.Ticker(symbol)
            raw_news = ticker.news or []

            news_items = []
            for item in raw_news[:limit]:
                news_item = self._parse_news_item(item)
                if news_item:
                    news_items.append(news_item)

            # Cache results
            self._cache[symbol] = (datetime.now(), news_items)

            logger.debug(f"Fetched {len(news_items)} news items for {symbol}")
            return news_items

        except Exception as e:
            logger.warning(f"Error fetching news for {symbol}: {e}")
            return []

    def _parse_news_item(self, raw: dict[str, Any]) -> NewsItem | None:
        """Parse a raw news item from yfinance."""
        try:
            # Extract timestamp
            published_at = None
            if "providerPublishTime" in raw:
                try:
                    published_at = datetime.fromtimestamp(raw["providerPublishTime"])
                except (ValueError, TypeError):
                    pass

            # Basic sentiment analysis from title
            sentiment = self._simple_sentiment(raw.get("title", ""))

            return NewsItem(
                title=raw.get("title", ""),
                summary=raw.get("summary", ""),
                link=raw.get("link", ""),
                publisher=raw.get("publisher", ""),
                published_at=published_at,
                sentiment_score=sentiment,
            )

        except Exception as e:
            logger.debug(f"Error parsing news item: {e}")
            return None

    def _simple_sentiment(self, text: str) -> float:
        """Simple keyword-based sentiment analysis.

        Returns a score between -1 (negative) and 1 (positive).
        This is a basic heuristic - could be replaced with a proper
        sentiment model for production use.
        """
        text = text.lower()

        positive_words = [
            "surge", "soar", "jump", "rally", "gain", "rise", "up",
            "beat", "exceed", "strong", "growth", "profit", "success",
            "upgrade", "buy", "bullish", "record", "high", "best",
            "boost", "improve", "positive", "outperform",
        ]

        negative_words = [
            "fall", "drop", "plunge", "crash", "decline", "down",
            "miss", "weak", "loss", "fail", "cut", "downgrade",
            "sell", "bearish", "low", "worst", "concern", "risk",
            "warning", "trouble", "crisis", "negative", "underperform",
        ]

        positive_count = sum(1 for word in positive_words if word in text)
        negative_count = sum(1 for word in negative_words if word in text)

        total = positive_count + negative_count
        if total == 0:
            return 0.0

        return (positive_count - negative_count) / total

    def get_market_sentiment(self, symbols: list[str]) -> dict[str, float]:
        """Get aggregate sentiment for multiple symbols.

        Args:
            symbols: List of ticker symbols.

        Returns:
            Dict mapping symbol to average sentiment score.
        """
        result = {}
        for symbol in symbols:
            news = self.get_news(symbol, limit=5)
            if news:
                scores = [n.sentiment_score for n in news if n.sentiment_score is not None]
                if scores:
                    result[symbol] = sum(scores) / len(scores)
                else:
                    result[symbol] = 0.0
            else:
                result[symbol] = 0.0
        return result

    def clear_cache(self, symbol: str | None = None) -> None:
        """Clear news cache.

        Args:
            symbol: Specific symbol to clear, or None to clear all.
        """
        if symbol:
            self._cache.pop(symbol, None)
        else:
            self._cache.clear()

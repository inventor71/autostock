"""Configured news access with explicit availability and runtime fallback."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from loguru import logger


@dataclass
class NewsResult:
    items: list = field(default_factory=list)
    status: str = "unavailable"
    provider: str | None = None
    fetched_at: datetime | None = None
    errors: list[str] = field(default_factory=list)

    def metadata(self) -> dict:
        now = datetime.now(UTC)
        dated = [it.published_at for it in self.items if getattr(it, "published_at", None)
                 and it.published_at.tzinfo is not None]
        ages = [(now - stamp).total_seconds() / 3600 for stamp in dated]
        recent = sum(0 <= age <= 24 for age in ages)
        content = "empty" if not self.items else "recent" if recent else (
            "old_only" if any(age > 24 for age in ages) else "undated_or_future")
        return {"status": self.status, "provider": self.provider,
                "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
                "content_status": content, "recent_items_24h": recent,
                "latest_published_at": max(dated).isoformat() if dated else None,
                "errors": self.errors}


def fetch_news(provider, symbol: str, limit: int = 8) -> NewsResult:
    """An empty successful feed is distinct from a failed/disabled feed."""
    if provider is None:
        return NewsResult(errors=["news:disabled"])
    if isinstance(provider, FallbackNewsProvider):
        return provider.fetch(symbol, limit)
    name = type(provider).__name__
    try:
        items = provider.get_news(symbol, limit=limit)
        stamp_fn = getattr(provider, "news_fetched_at", None)
        stamp = stamp_fn(symbol) if callable(stamp_fn) else datetime.now(UTC)
        return NewsResult(items=items, status="ok", provider=name, fetched_at=stamp)
    except Exception as exc:  # noqa: BLE001 — provider failure is a first-class result
        # Exception text can contain request URLs/credentials. Expose types only.
        return NewsResult(provider=name, errors=[f"{name}:{type(exc).__name__}"])


class FallbackNewsProvider:
    def __init__(self, providers: list[tuple[str, object | None]]):
        self.providers = providers

    def fetch(self, symbol: str, limit: int = 8) -> NewsResult:
        errors = []
        available = None
        for name, provider in self.providers:
            result = fetch_news(provider, symbol, limit)
            if result.status == "ok":
                result.provider = name
                content = result.metadata()["content_status"]
                if content == "recent" or (content == "empty" and available is None):
                    result.errors = errors
                    return result
                if content == "empty":
                    continue
                # A working endpoint can serve only old/undated articles. Try
                # the configured alternative, retaining usable older context if
                # that also fails. Never relabel the old articles as fresh.
                stamp = result.metadata()["latest_published_at"]
                prior = available.metadata()["latest_published_at"] if available else None
                if available is None or (stamp and (not prior or datetime.fromisoformat(stamp) > datetime.fromisoformat(prior))):
                    available = result
                errors.append(f"{name}:no_recent_dated_items")
                continue
            errors.extend([f"{name}:not_configured"] if provider is None else result.errors)
        if available is not None:
            available.errors = errors
            return available
        return NewsResult(errors=errors or ["news:disabled"])

    def get_news(self, symbol: str, limit: int = 8) -> list:
        result = self.fetch(symbol, limit)
        if result.status != "ok":
            raise RuntimeError("News unavailable: " + ", ".join(result.errors))
        return result.items


def build_news_provider(settings=None, config=None) -> FallbackNewsProvider:
    from config.config import get_settings
    from src.signals.settings import SignalsConfig

    settings = settings if settings is not None else get_settings()
    config = config if config is not None else SignalsConfig.from_settings(settings.signals)
    providers = []
    for name in dict.fromkeys((config.sources.news_primary, config.sources.news_fallback)):
        provider = None
        if name == "none":
            continue
        if name == "alpaca" and settings.alpaca_api_key and settings.alpaca_api_secret:
            from src.signals.sources.alpaca_news import AlpacaNewsProvider
            try:
                provider = AlpacaNewsProvider(
                    settings.alpaca_api_key, settings.alpaca_api_secret,
                    http_connect_timeout=config.http_connect_timeout,
                    http_read_timeout=config.http_read_timeout,
                )
            except Exception as exc:  # noqa: BLE001 — optional provider initialization
                logger.warning("Alpaca news setup unavailable: {}", type(exc).__name__)
        elif name == "yfinance":
            from src.data.providers.news_provider import YFinanceNewsProvider
            provider = YFinanceNewsProvider()
        providers.append((name, provider))
    return FallbackNewsProvider(providers)

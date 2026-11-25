"""Regression tests for the real settings/tool boundary and source provenance."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from config.config import Settings
from src.agent.tools import market
from src.data.news import FallbackNewsProvider, fetch_news
from src.data.providers.news_provider import NewsItem, YFinanceNewsProvider


class Feed:
    def __init__(self, items=(), error=None):
        self.items, self.error, self.calls = list(items), error, 0

    def get_news(self, symbol, limit=8):
        self.calls += 1
        if self.error:
            raise self.error
        return self.items[:limit]


def test_news_runtime_fallback_and_recovery_do_not_turn_errors_into_empty_news():
    primary = Feed(error=TimeoutError("sensitive request text"))
    fallback = Feed([NewsItem(title="New filing", published_at=datetime.now(UTC))])
    provider = FallbackNewsProvider([("primary", primary), ("fallback", fallback)])
    result = market.news("AAPL", provider)
    assert result["provider"] == "fallback" and result["status"] == "ok"
    assert result["news"][0]["title"] == "New filing"
    assert result["errors"] == ["Feed:TimeoutError"]
    assert "sensitive" not in str(result)
    primary.error = None
    recovered = market.news("AAPL", provider)
    assert recovered["provider"] == "primary" and recovered["status"] == "ok"
    assert recovered["news"] == []  # a genuinely empty successful feed
    assert fallback.calls == 1


def test_all_failed_news_remains_explicitly_unavailable():
    provider = FallbackNewsProvider([("primary", Feed(error=TimeoutError())), ("fallback", None)])
    result = market.news("AAPL", provider)
    assert result["status"] == "unavailable" and result["news"] == [] and result["errors"]
    with pytest.raises(RuntimeError, match="unavailable"):
        provider.get_news("AAPL")  # older list consumers can also detect failure


def test_yahoo_failure_is_not_cached_as_an_empty_success(monkeypatch):
    provider = YFinanceNewsProvider()

    def failed(_):
        raise RuntimeError("YAHOO DOWN")

    monkeypatch.setattr("src.data.providers.news_provider.yf.Ticker", failed)
    assert fetch_news(provider, "AAPL").status == "unavailable"
    monkeypatch.setattr("src.data.providers.news_provider.yf.Ticker", lambda _: SimpleNamespace(news=[]))
    result = fetch_news(provider, "AAPL")
    assert result.status == "ok" and result.items == []
    assert result.fetched_at.tzinfo is not None


def test_cached_news_keeps_original_fetch_time_and_article_publication_time(monkeypatch):
    fetched = datetime.now(UTC) - timedelta(minutes=5)
    published = fetched - timedelta(days=2)
    provider = YFinanceNewsProvider()
    provider._cache["AAPL"] = (fetched, [NewsItem(title="Old catalyst", published_at=published)])
    monkeypatch.setattr("src.data.providers.news_provider.yf.Ticker", lambda _: pytest.fail("must use cache"))
    result = market.news("aapl", provider)
    assert result["fetched_at"] == fetched.isoformat()
    assert result["news"][0]["published_at"] == published.isoformat()
    assert result["news"][0]["priced_in_risk"] == "elevated"


def test_news_cli_uses_configured_primary(monkeypatch, capsys):
    import json

    from src.agent.tools import __main__ as cli

    settings = Settings(_env_file=None, alpaca_api_key="test", alpaca_api_secret="test",
                        signals={"sources": {"news_primary": "alpaca", "news_fallback": "yfinance"}})
    monkeypatch.setattr("config.config.get_settings", lambda: settings)
    feed = Feed([NewsItem(title="Configured feed", published_at=datetime.now(UTC))])
    monkeypatch.setattr("src.signals.sources.alpaca_news.AlpacaNewsProvider", lambda *a, **k: feed)
    monkeypatch.delenv("AUTOSTOCK_TOOLS_FIXTURE_DIR", raising=False)
    monkeypatch.delenv("AUTOSTOCK_TOOLS_RECORD_DIR", raising=False)
    assert cli.main(["news", "AAPL"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["provider"] == "alpaca" and result["news"][0]["title"] == "Configured feed"


@pytest.mark.parametrize("command", ["movers", "earnings_calendar", "ipo_calendar"])
def test_signal_cli_works_with_real_settings_and_reports_disabled_sources(monkeypatch, capsys, command):
    import json

    from src.agent.tools import __main__ as cli

    settings = Settings(_env_file=None, universe={"override": ["AAPL"]},
                        alpaca_api_key="", alpaca_api_secret="", finnhub_api_key="",
                        signals={"sources": {"news_fallback": "none"}})
    assert not hasattr(settings.trading, "symbols")  # reproduce the production schema
    monkeypatch.setattr("config.config.get_settings", lambda: settings)
    monkeypatch.setattr(cli, "_provider", lambda: SimpleNamespace(get_bars=lambda *a, **k: pd.DataFrame()))
    closed = []
    monkeypatch.setattr(cli, "_broker", lambda: SimpleNamespace(
        get_portfolio_state=lambda: SimpleNamespace(positions={"HELD_OUTSIDE_POOL": None}),
        close=lambda: closed.append(True)))
    monkeypatch.delenv("AUTOSTOCK_TOOLS_FIXTURE_DIR", raising=False)
    monkeypatch.delenv("AUTOSTOCK_TOOLS_RECORD_DIR", raising=False)
    assert cli.main([command]) == 0
    result = json.loads(capsys.readouterr().out)
    assert "earnings:disabled" in result["degraded_sources"]
    assert "prices:AAPL" in result["degraded_sources"] and closed


def test_signal_cli_keeps_shadow_frozen_universe(monkeypatch):
    from src.agent.tools import __main__ as cli

    settings = Settings(_env_file=None, broker={"provider": "toss_shadow"},
                        universe={"override": ["NEW_CONFIG_NAME"]},
                        alpaca_api_key="", alpaca_api_secret="", finnhub_api_key="")
    monkeypatch.setattr("config.config.get_settings", lambda: settings)
    monkeypatch.setattr(cli, "_provider", lambda: object())
    monkeypatch.setattr(cli, "_broker", lambda: SimpleNamespace(
        read=lambda: {"universe": ["FROZEN"]}, close=lambda: None))
    assert cli._signal_collector().universe == ["FROZEN"]


class Prices:
    def get_bars(self, *args, **kwargs):
        return pd.DataFrame({"open": [90., 100.], "high": [92., 102.], "low": [89., 99.],
                             "close": [91., 101.], "volume": [10, 20]},
                            index=pd.date_range("2026-11-22", periods=2, tz="America/New_York"))

    def get_latest_quote(self, _):
        return {"price": 105., "source_as_of": "2026-11-24T15:30:00Z"}


def test_previous_daily_close_cannot_masquerade_as_the_current_quote():
    result = market.quote("AAPL", Prices())
    assert result["price"] == 101 and result["timeframe"] == "1d"
    assert result["source_as_of"].startswith("2026-11-23")
    assert result["latest_quote"]["price"] == 105
    assert result["latest_quote"]["source_as_of"] == "2026-11-24T15:30:00Z"
    assert market.scoreboard(["AAPL"], Prices())[0]["source_as_of"] == result["source_as_of"]


def test_quote_still_exposes_current_price_when_daily_history_fails():
    class BrokenDaily(Prices):
        def get_bars(self, *args, **kwargs):
            raise TimeoutError()

    result = market.quote("AAPL", BrokenDaily())
    assert result["latest_quote"]["price"] == 105 and result["error"] == "TimeoutError"


def test_macro_exposes_actual_per_series_source_times():
    provider = SimpleNamespace(Ticker=lambda _: SimpleNamespace(
        history=lambda **k: pd.DataFrame({"Close": [100., 101.]},
                                        index=pd.date_range("2026-11-22", periods=2, tz="UTC"))))
    result = market.macro(provider)
    assert result["as_of"] is None
    assert result["gold"]["source_as_of"] == "2026-11-23T00:00:00+00:00"
    assert result["gold"]["timeframe"] == "1d"
    assert result["retrieved_at"] != result["gold"]["source_as_of"]


def test_old_primary_news_tries_fallback_but_remains_visible_when_it_fails():
    primary = Feed([NewsItem(title="Old", published_at=datetime.now(UTC) - timedelta(days=18))])
    alternative = Feed([NewsItem(title="Current", published_at=datetime.now(UTC))])
    provider = FallbackNewsProvider([("primary", primary), ("alternative", alternative)])
    result = market.news("QQQ", provider)
    assert result["provider"] == "alternative" and result["content_status"] == "recent"
    alternative.error = TimeoutError()
    result = market.news("QQQ", provider)
    assert result["status"] == "ok" and result["content_status"] == "old_only"
    assert result["news"][0]["title"] == "Old"
    assert result["recent_items_24h"] == 0 and "Feed:TimeoutError" in result["errors"]

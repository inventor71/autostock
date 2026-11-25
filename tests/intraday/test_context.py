"""Observed changes, gaps and prices must reach the actual scheduled prompts."""
import json
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from src.agent.intraday.bars import BarCache
from src.agent.intraday.context import IntradayContext
from src.agent.intraday.settings import IntradayConfig
from src.data.providers.news_provider import NewsItem
from src.monitoring.research import read_context_summary


class Prices:
    price = 101.
    error = False

    def get_latest_quote(self, symbol):
        if self.error:
            raise TimeoutError()
        return {"price": self.price, "source_as_of": datetime.now(UTC).isoformat()}

    def get_bars(self, *args, **kwargs):
        if self.error:
            raise TimeoutError()
        return pd.DataFrame({"open": [100., 100.], "high": [102., 103.], "low": [99., 99.],
                             "close": [100., 101.], "volume": [10, 20]},
                            index=pd.date_range(datetime.now(UTC) - timedelta(minutes=10), periods=2, freq="5min"))


class News:
    title = "New earnings guidance"

    def get_news(self, symbol, limit=8):
        return [NewsItem(title=f"{symbol} {self.title}", published_at=datetime.now(UTC), link="https://example.test/filing")]


def test_context_covers_positions_watchlist_and_market_and_persists_gaps(tmp_path):
    (tmp_path / "watchlist.md").write_text("Watch V; OUTSIDE is not in the tradeable pool.")
    prices, news = Prices(), News()
    context = IntradayContext(
        prices, tmp_path, snapshot_fn=lambda: {"positions": {"AAPL": {"qty": 10}}, "cash": 1000},
        universe=["AAPL", "V"], news_provider=news,
        config=IntradayConfig(market_symbols=("SPY", "QQQ"), price_cache_seconds=0, bars_cache_seconds=0))
    first = context.build()
    for symbol in ("AAPL", "V", "SPY", "QQQ"):
        assert f"{symbol} New earnings guidance" in first
    assert "OUTSIDE" not in first
    assert "published=" in first and "bars=5m@" in first
    assert read_context_summary(tmp_path)["status"] == "ok"
    prices.error = True
    context.build()
    record = json.loads((tmp_path / "research-context.json").read_text())
    assert record["market_data"]["AAPL"]["quote"]["status"] == "cached_after_error"
    assert read_context_summary(tmp_path)["status"] == "degraded"
    prices.error = False
    prices.price = 105
    news.title = "Guidance cut since last turn"
    latest = context.build()
    assert "px=105.00" in latest and "Guidance cut since last turn" in latest
    assert read_context_summary(tmp_path)["status"] == "ok"
    assert len((tmp_path / "research-context.jsonl").read_text().splitlines()) == 3
    assert (tmp_path / "research-context.json").stat().st_mode & 0o777 == 0o600


def test_cached_old_quote_is_not_relabelled_with_the_current_time():
    old = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    class Old(Prices):
        def get_latest_quote(self, symbol):
            if self.error:
                raise TimeoutError()
            return {"price": 101, "source_as_of": old}

    provider = Old()
    cache = BarCache(provider, price_ttl=0)
    assert cache.get_price("AAPL") == 101
    original = cache.coverage("AAPL")["quote"]
    provider.error = True
    assert cache.get_price("AAPL") == 101
    cached = cache.coverage("AAPL")["quote"]
    assert cached["source_as_of"] == old
    assert cached["retrieved_at"] == original["retrieved_at"]
    assert cached["source_age_seconds"] > 86000 and cached["status"] == "cached_after_error"


def test_missing_quote_time_and_account_failure_are_explicit(tmp_path):
    class NoSourceTime(Prices):
        def get_latest_quote(self, symbol):
            return {"price": 101.}

    def broken_account():
        raise TimeoutError()

    context = IntradayContext(NoSourceTime(), tmp_path, snapshot_fn=broken_account,
                              news_provider=News(), config=IntradayConfig(market_symbols=("SPY",)))
    assert "ACCOUNT incomplete: TimeoutError" in context.build()
    summary = read_context_summary(tmp_path)
    assert summary["account_error"] == "TimeoutError"
    assert summary["quote_time_unknown"] == ["SPY"]


@pytest.mark.parametrize("steering_enabled", [False, True])
def test_normal_scheduled_turn_receives_updated_context(tmp_path, monkeypatch, steering_enabled):
    from src.agent.executor import DecisionExecutor
    from src.agent.journal import Journal
    from src.agent.steering.runtime import SteeringRuntime
    from src.execution.brokers.simulated_broker import SimulatedBroker
    from src.risk.manager import RiskManager
    from src.trading.modes.agent import AgentTradingMode

    monkeypatch.setenv("AGENT_JOURNAL_ROOT", str(tmp_path))

    class Loop:
        def __init__(self):
            self.prompts = []

        def run_intraday(self, brief):
            self.prompts.append(brief)

    prices, news, loop = Prices(), News(), Loop()
    broker = SimulatedBroker(initial_capital=1000)
    journal = Journal(tmp_path)
    journal.init()
    journal.write_watchlist("Watch V")
    executor = DecisionExecutor(broker, RiskManager(use_bracket_orders=True), prices, journal=journal, universe=["V"])
    steering = SteeringRuntime(executor, loop, steering_dir=tmp_path / "steering", token="test") if steering_enabled else None
    monkeypatch.setattr(AgentTradingMode, "_news_provider", staticmethod(lambda: news))
    mode = AgentTradingMode(loop, executor, steering=steering,
                           intraday_config=IntradayConfig(market_symbols=("SPY",), price_cache_seconds=0))
    if steering:
        steering.start()
    try:
        mode._intraday()
        prices.price = 106
        news.title = "Current-session warning"
        mode._intraday()
        assert len(loop.prompts) == 2
        assert "V New earnings guidance" in loop.prompts[0]
        assert "V Current-session warning" in loop.prompts[1]
        assert "SPY" in loop.prompts[1] and "px=106.00" in loop.prompts[1]
        assert "NEWS coverage" in loop.prompts[1]
        assert broker.get_portfolio_state().cash == 1000
        assert broker.get_open_orders() == []
    finally:
        mode.stop()

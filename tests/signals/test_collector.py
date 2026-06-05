"""Tests for SignalCollector — fail-honest wiring of the pure core (F61, NFR-1)."""

from __future__ import annotations

from datetime import date

import pytest

from src.signals.collector import SignalCollector
from src.signals.records import EarningsRow
from src.signals.settings import SignalsConfig

_TODAY = date(2026, 6, 5)
_UNIVERSE = ["AVGO", "NVDA", "AMD", "MRVL"]
_CONFIG = SignalsConfig(
    price_pct=5.0, vol_ratio=2.0, readthrough_min_pct=7.0,
    peer_groups={"semis": ["AVGO", "NVDA", "AMD", "MRVL"]},
    cache_ttl_seconds=300.0,
)


class _Headline:
    def __init__(self, title):
        self.title = title


class _FakeNews:
    def __init__(self, raises=False):
        self.raises = raises

    def get_news(self, symbol, limit=3):
        if self.raises:
            raise RuntimeError("news boom")
        return [_Headline(f"{symbol} earnings guidance miss")]


class _FakeEarnings:
    def __init__(self, rows=None, raises=False):
        self.rows = rows or []
        self.raises = raises

    def get_calendar(self, from_date, to_date):
        if self.raises:
            raise RuntimeError("finnhub boom")
        return self.rows


def _scoreboard_rows(*rows):
    """rows: (symbol, chg_1d, vol_ratio) → scoreboard-shaped dicts."""
    return [{"symbol": s, "chg_1d": c, "vol_ratio": v, "close": 10.0} for s, c, v in rows]


@pytest.fixture
def patch_scoreboard(monkeypatch):
    def _patch(rows):
        monkeypatch.setattr("src.agent.tools.market.scoreboard", lambda syms, prov: rows)
    return _patch


def _collector(news=None, earnings=None):
    return SignalCollector(
        config=_CONFIG, universe=_UNIVERSE, price_provider=object(),
        news_provider=news, earnings_source=earnings,
    )


def test_happy_path(patch_scoreboard):
    patch_scoreboard(_scoreboard_rows(("AVGO", -15.0, 3.0), ("NVDA", -2.0, 1.0)))
    earnings = _FakeEarnings([EarningsRow(symbol="NVDA", earnings_date=date(2026, 6, 6), when="amc")])
    brief = _collector(news=_FakeNews(), earnings=earnings).collect(today=_TODAY)

    assert {m.symbol for m in brief.movers} == {"AVGO"}
    assert len(brief.readthrough_alerts) == 1
    alert = brief.readthrough_alerts[0]
    assert alert.trigger_symbol == "AVGO"
    assert set(alert.affected_peers) == {"NVDA", "AMD", "MRVL"}
    assert alert.cause_hint and "guidance" in alert.cause_hint
    assert {e.symbol for e in brief.imminent_earnings} == {"NVDA"}
    assert brief.degraded_sources == []


def test_news_failure_degrades_not_crashes(patch_scoreboard):
    patch_scoreboard(_scoreboard_rows(("AVGO", -15.0, 3.0)))
    brief = _collector(news=_FakeNews(raises=True), earnings=_FakeEarnings()).collect(today=_TODAY)
    assert brief.readthrough_alerts  # alert still produced
    assert brief.readthrough_alerts[0].cause_hint is None
    assert "news" in brief.degraded_sources


def test_no_earnings_source_marked_disabled(patch_scoreboard):
    patch_scoreboard(_scoreboard_rows(("AVGO", -15.0, 3.0)))
    brief = _collector(news=_FakeNews(), earnings=None).collect(today=_TODAY)
    assert "earnings:disabled" in brief.degraded_sources
    assert brief.imminent_earnings == []


def test_earnings_failure_degrades(patch_scoreboard):
    patch_scoreboard(_scoreboard_rows(("AVGO", -15.0, 3.0)))
    brief = _collector(news=_FakeNews(), earnings=_FakeEarnings(raises=True)).collect(today=_TODAY)
    assert "earnings:finnhub" in brief.degraded_sources


def test_scoreboard_failure_degrades(monkeypatch):
    def boom(syms, prov):
        raise RuntimeError("scoreboard boom")

    monkeypatch.setattr("src.agent.tools.market.scoreboard", boom)
    brief = _collector(news=_FakeNews(), earnings=_FakeEarnings()).collect(today=_TODAY)
    assert brief.movers == []
    assert "prices:scoreboard" in brief.degraded_sources


def test_cache_returns_same_object(patch_scoreboard):
    patch_scoreboard(_scoreboard_rows(("AVGO", -15.0, 3.0)))
    collector = _collector(news=_FakeNews(), earnings=_FakeEarnings())
    b1 = collector.collect(today=_TODAY)
    b2 = collector.collect(today=_TODAY)
    assert b1 is b2

"""F96 — news freshness surface (market.news age_hours + priced_in_risk).

Deterministic: the comparison clock is injected via ``_now`` so no wall-clock.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.agent.tools import market
from src.agent.tools.market import _news_age_hours, _priced_in_risk
from src.data.providers.news_provider import NewsItem

_NOW = datetime(2026, 6, 1, 12, 0, 0)


class TestAgeHours:
    def test_recent(self):
        pub = _NOW - timedelta(hours=2)
        assert _news_age_hours(pub, _NOW) == 2.0

    def test_old(self):
        pub = _NOW - timedelta(hours=30)
        assert _news_age_hours(pub, _NOW) == 30.0

    def test_missing_is_none(self):
        assert _news_age_hours(None, _NOW) is None

    def test_tz_aware_pub_naive_now_aligns(self):
        # aware published_at + naive injected now must not raise (awareness aligned).
        pub = (_NOW - timedelta(hours=5)).replace(tzinfo=timezone.utc)
        assert _news_age_hours(pub, _NOW) == 5.0


class TestPricedInRisk:
    def test_fresh_below_threshold(self):
        assert _priced_in_risk(2.0) == "fresh"

    def test_boundary_24h_is_fresh(self):
        # exactly at the threshold is NOT "> threshold" -> still fresh.
        assert _priced_in_risk(24.0) == "fresh"

    def test_just_over_is_elevated(self):
        assert _priced_in_risk(24.5) == "elevated"

    def test_unknown_is_none(self):
        assert _priced_in_risk(None) is None


class TestNewsToolIntegration:
    def _tool(self, published_at):
        class FakeNews:
            def get_news(self, symbol, limit=8):
                return [NewsItem(title="T", publisher="P", link="L", published_at=published_at)]

        return market.news("AAPL", news_provider=FakeNews(), _now=_NOW)

    def test_fresh_item_fields(self):
        item = self._tool(_NOW - timedelta(hours=3))["news"][0]
        assert item["age_hours"] == 3.0
        assert item["priced_in_risk"] == "fresh"

    def test_elevated_item_fields(self):
        item = self._tool(_NOW - timedelta(hours=40))["news"][0]
        assert item["age_hours"] == 40.0
        assert item["priced_in_risk"] == "elevated"

    def test_missing_date_fields_none(self):
        item = self._tool(None)["news"][0]
        assert item["age_hours"] is None
        assert item["priced_in_risk"] is None
        assert item["published_at"] is None

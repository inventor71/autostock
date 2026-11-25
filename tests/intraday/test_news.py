"""Step 7 — NewsPoller: new-headline diff, dedup, persistence, fault-tolerance."""

from __future__ import annotations

import json

from src.agent.intraday.news_diff import NewsPoller


class _Item:
    def __init__(self, title):
        self.title = title


class _News:
    def __init__(self, by_symbol):
        self._by = by_symbol  # symbol -> list[list[title]] (one per poll)
        self._i = {}

    def get_news(self, symbol, limit=8):
        seq = self._by.get(symbol, [[]])
        idx = min(self._i.get(symbol, 0), len(seq) - 1)
        self._i[symbol] = self._i.get(symbol, 0) + 1
        return [_Item(t) for t in seq[idx]]


def test_only_new_headlines_surface(tmp_path):
    # poll 1: [h1] -> all new; poll 2: [h2, h1] -> only h2 is new.
    np = _News({"AAPL": [["h1"], ["h2", "h1"]]})
    poller = NewsPoller(np, tmp_path, ttl_minutes=15)

    poller.poll_once(["AAPL"])
    assert poller.diff_for(["AAPL"])["AAPL"].headlines == ["h1"]

    poller.poll_once(["AAPL"])
    assert poller.diff_for(["AAPL"])["AAPL"].headlines == ["h2"]


def test_polling_does_not_discard_news_before_the_next_model_turn(tmp_path):
    np = _News({"AAPL": [["h1"], ["h1"]]})  # second poll: nothing new
    poller = NewsPoller(np, tmp_path)
    poller.poll_once(["AAPL"])
    poller.poll_once(["AAPL"])
    assert poller.diff_for(["AAPL"])["AAPL"].headlines == ["h1"]
    poller.poll_once(["AAPL"])
    assert poller.diff_for(["AAPL"]) == {}


def test_last_seen_persisted(tmp_path):
    np = _News({"AAPL": [["h1"]]})
    poller = NewsPoller(np, tmp_path)
    poller.poll_once(["AAPL"])
    assert not (tmp_path / ".news_seen.json").exists()  # not yet delivered
    poller.diff_for(["AAPL"])
    data = json.loads((tmp_path / ".news_seen.json").read_text())
    assert data["AAPL"] == "h1"


def test_poll_tolerates_provider_failure(tmp_path):
    class _Dead:
        def get_news(self, symbol, limit=8):
            raise RuntimeError("rate limited")

    poller = NewsPoller(_Dead(), tmp_path)
    poller.poll_once(["AAPL"])  # must not raise (NFR-4)
    assert poller.diff_for(["AAPL"]) == {}
    assert poller.coverage_for(["AAPL"])["AAPL"]["status"] == "unavailable"


def test_unread_news_survives_polls_failure_and_restart(tmp_path):
    np = _News({"AAPL": [["h1"], ["h2", "h1"], ["h2", "h1"]]})
    poller = NewsPoller(np, tmp_path)
    for _ in range(3):
        poller.poll_once(["AAPL"])
    assert poller.diff_for(["AAPL"])["AAPL"].headlines == ["h2", "h1"]
    restarted = NewsPoller(np, tmp_path)
    restarted.poll_once(["AAPL"])
    assert restarted.diff_for(["AAPL"]) == {}


def test_unchecked_empty_failed_and_recovered_feed_are_distinct(tmp_path):
    class Flaky:
        failed = False

        def get_news(self, *args, **kwargs):
            if self.failed:
                raise TimeoutError("provider down")
            return []

    provider = Flaky()
    poller = NewsPoller(provider, tmp_path)
    assert poller.coverage_for(["AAPL"])["AAPL"]["status"] == "not_checked"
    poller.poll_once(["AAPL"])
    assert poller.coverage_for(["AAPL"])["AAPL"]["status"] == "ok"
    provider.failed = True
    poller.poll_once(["AAPL"])
    assert poller.coverage_for(["AAPL"])["AAPL"]["status"] == "unavailable"
    provider.failed = False
    poller.poll_once(["AAPL"])
    assert poller.coverage_for(["AAPL"])["AAPL"]["status"] == "ok"


def test_slow_feed_does_not_block_a_turn_or_spawn_duplicate_workers(tmp_path):
    import threading

    entered, release = threading.Event(), threading.Event()
    calls = []

    class Slow:
        def get_news(self, symbol, limit=8):
            calls.append(symbol)
            entered.set()
            release.wait(2)
            return [_Item("late headline")]

    poller = NewsPoller(Slow(), tmp_path)
    try:
        poller.refresh(["AAPL"], timeout=0)
        assert entered.wait(1)
        poller.refresh(["AAPL"], timeout=0)
        assert calls == ["AAPL"]
        assert poller.coverage_for(["AAPL"])["AAPL"]["status"] == "not_checked"
    finally:
        release.set()
        poller._refresh_thread.join(2)
    assert poller.diff_for(["AAPL"])["AAPL"].headlines == ["late headline"]


def test_fresh_fetch_with_old_articles_is_reported_as_a_recency_gap(tmp_path):
    from datetime import UTC, datetime, timedelta

    from src.data.providers.news_provider import NewsItem

    class Old:
        def get_news(self, *args, **kwargs):
            return [NewsItem(title="Old report", published_at=datetime.now(UTC) - timedelta(days=18))]

    poller = NewsPoller(Old(), tmp_path)
    poller.poll_once(["QQQ"])
    row = poller.coverage_for(["QQQ"])["QQQ"]
    assert row["fetch_age_seconds"] < 2
    assert row["content_status"] == "old_only"
    assert row["status"] == "no_recent_dated_items"

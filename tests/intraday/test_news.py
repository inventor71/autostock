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


def test_no_new_headlines_clears_diff(tmp_path):
    np = _News({"AAPL": [["h1"], ["h1"]]})  # second poll: nothing new
    poller = NewsPoller(np, tmp_path)
    poller.poll_once(["AAPL"])
    poller.poll_once(["AAPL"])
    assert poller.diff_for(["AAPL"]) == {}


def test_last_seen_persisted(tmp_path):
    np = _News({"AAPL": [["h1"]]})
    poller = NewsPoller(np, tmp_path)
    poller.poll_once(["AAPL"])
    data = json.loads((tmp_path / ".news_seen.json").read_text())
    assert data["AAPL"] == "h1"


def test_poll_tolerates_provider_failure(tmp_path):
    class _Dead:
        def get_news(self, symbol, limit=8):
            raise RuntimeError("rate limited")

    poller = NewsPoller(_Dead(), tmp_path)
    poller.poll_once(["AAPL"])  # must not raise (NFR-4)
    assert poller.diff_for(["AAPL"]) == {}

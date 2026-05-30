"""Review fixes #4/#9 — session_open anchor + shared held_and_watched helper."""

from __future__ import annotations

import pandas as pd

from src.agent.intraday.util import held_and_watched, session_open


def test_session_open_uses_first_bar_of_latest_day_not_oldest():
    # Window spans two days; ref must be the LATEST day's first open (session open),
    # not the oldest bar in the rolling window (review #4).
    idx = pd.to_datetime([
        "2026-05-29 15:50", "2026-05-29 15:55",   # prior day
        "2026-05-30 09:30", "2026-05-30 09:35",   # today
    ])
    bars = pd.DataFrame({"open": [500, 501, 610, 615], "high": [0, 0, 0, 0],
                         "low": [0, 0, 0, 0], "close": [0, 0, 0, 0],
                         "volume": [1, 1, 1, 1]}, index=idx)
    assert session_open(bars) == 610.0  # today's open, not 500 (oldest)


def test_session_open_single_day_falls_back_to_first():
    idx = pd.to_datetime(["2026-05-30 09:30", "2026-05-30 09:35"])
    bars = pd.DataFrame({"open": [610, 615], "high": [0, 0], "low": [0, 0],
                         "close": [0, 0], "volume": [1, 1]}, index=idx)
    assert session_open(bars) == 610.0


def test_session_open_none_on_empty():
    assert session_open(None) is None


class _WT:
    def __init__(self, symbol):
        self.symbol = symbol


class _Watch:
    def __init__(self, syms):
        self._t = [_WT(s) for s in syms]

    def active(self):
        return self._t


def test_held_and_watched_dedups_held_and_watched():
    snap = {"positions": {"AAPL": {}, "MSFT": {}}}
    out = held_and_watched(snap, _Watch(["MSFT", "RTX"]))
    assert out == ["AAPL", "MSFT", "RTX"]  # order preserved, deduped


def test_held_and_watched_tolerates_none_and_watch_failure():
    class _Bad:
        def active(self):
            raise RuntimeError("boom")

    assert held_and_watched(None, None) == []
    assert held_and_watched({"positions": {"AAPL": {}}}, _Bad()) == ["AAPL"]

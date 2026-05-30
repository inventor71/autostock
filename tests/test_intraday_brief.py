"""Step 6 — BriefAssembler: snapshot-only data, human-context, fail-closed."""

from __future__ import annotations

import pandas as pd

from src.agent.intraday.bars import BarCache
from src.agent.intraday.brief import BriefAssembler


class _Provider:
    def __init__(self):
        self.position_calls = 0  # must stay 0 — brief never touches the broker

    def get_latest_price(self, symbol):
        return 101.0

    def get_bars(self, symbol, timeframe=None, limit=50):
        idx = pd.date_range("2026-05-30 09:30", periods=3, freq="5min")
        return pd.DataFrame({"open": [100, 101, 101], "high": [102, 103, 102],
                             "low": [99, 100, 100], "close": [101, 102, 101],
                             "volume": [10, 20, 30]}, index=idx)


class _Directive:
    text = "trim tech exposure"


class _State:
    def active_directives(self):
        return [_Directive()]


def _snapshot():
    return {
        "positions": {"AAPL": {"qty": 10, "avg_entry_price": 100.0}},
        "open_orders": [{"symbol": "AAPL", "order_id": "o1", "stop_price": 98.0,
                         "limit_price": None}],
        "fills": [{"side": "buy", "qty": 5, "symbol": "META", "price": 631.2}],
        "locked_symbols": {"AAPL": "locked"},
        "pending": [{"id": "p1"}],
        "run_state": {"paused": False},
    }


def test_brief_includes_levels_human_and_delta():
    cache = BarCache(_Provider())
    brief = BriefAssembler(cache, state=_State()).build(snapshot=_snapshot())
    assert "INTRADAY BRIEF" in brief
    assert "AAPL" in brief and "px=101.00" in brief and "stop=98.0" in brief
    assert "HUMAN: directives=[trim tech exposure]" in brief
    assert "pending_approvals=1" in brief and "locked=['AAPL']" in brief
    assert "DELTA new_fills:" in brief and "META@631.2" in brief


def test_brief_fail_closed_without_snapshot():
    cache = BarCache(_Provider())
    out = BriefAssembler(cache).build(snapshot=None)
    assert "no live account snapshot" in out


def test_brief_held_symbols_come_from_snapshot_not_broker():
    # No broker is provided anywhere; held symbols derive from snapshot positions.
    cache = BarCache(_Provider())
    brief = BriefAssembler(cache).build(snapshot=_snapshot())
    # AAPL (a snapshot position) is present without any broker.get_position call.
    assert "  AAPL" in brief


def test_brief_includes_news_when_present():
    from src.agent.intraday.records import NewsDiff
    cache = BarCache(_Provider())
    news = {"AAPL": NewsDiff(symbol="AAPL", headlines=["AAPL unveils chip"])}
    brief = BriefAssembler(cache).build(snapshot=_snapshot(), news=news)
    assert "NEWS (new): AAPL: AAPL unveils chip" in brief


def test_brief_renders_active_watch_levels():
    class _WT:
        symbol = "RTX"
        condition = "close_above"
        level = 182.0

    class _Watch:
        def active(self):
            return [_WT()]

    cache = BarCache(_Provider())
    brief = BriefAssembler(cache, watch_store=_Watch()).build(snapshot=_snapshot())
    assert "RTX" in brief and "watch=close_above 182.0" in brief

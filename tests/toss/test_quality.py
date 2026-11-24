import copy
from datetime import UTC, datetime, timedelta

import pytest

from src.execution.brokers.toss.quality import quote_quality

NOW = datetime(2026, 11, 23, 15, tzinfo=UTC)


def portfolio():
    positions = {"AAPL": {"qty": 90}, "SGOV": {"qty": 0.5}, "ATI": {"qty": 0.5}}
    return {"cash": 900, "positions": positions,
            "initial": {"cash": 900, "positions": copy.deepcopy(positions)}, "orders": {},
            "marks": {s: {"price": 100, "source_at": (NOW - timedelta(seconds=age)).isoformat()}
                      for s, age in [("AAPL", 0), ("SGOV", 30), ("ATI", 30)]},
            "execution": {"max_quote_age": 15}}


def test_aggregate_stale_value_uses_both_books_and_cash():
    state = portfolio()  # $100 of $10,000 is indicative: exactly the 1% boundary.
    quality = quote_quality(state, NOW, {"AAPL"}, {})
    assert quality["valuation_usable"] and not quality["all_quotes_fresh"]
    assert quality["fresh_value_pct"] == {"strategy": 99, "hold": 99}
    state["initial"]["positions"]["SGOV"]["qty"] += 0.01
    assert not quote_quality(state, NOW, {"AAPL"}, {})["valuation_usable"]
    state = portfolio()
    state["positions"]["ATI"]["qty"] += 0.01
    assert not quote_quality(state, NOW, {"AAPL"}, {})["valuation_usable"]


@pytest.mark.parametrize("age", [120.001, -1, None])
def test_age_bound_and_unknown_source_fail_even_for_tiny_holdings(age):
    state = portfolio()
    state["marks"]["SGOV"]["source_at"] = (NOW - timedelta(seconds=age)).isoformat() if age is not None else None
    quality = quote_quality(state, NOW, {"AAPL"}, {})
    assert quality["status"] == "unavailable"
    assert "SGOV" in quality["unavailable_symbols"]


def test_failed_book_is_unavailable_even_if_previous_mark_is_recent():
    state = portfolio()
    quality = quote_quality(state, NOW, set(state["positions"]), {"SGOV": "invalid orderbook"})
    assert not quality["valuation_usable"] and not quality["all_quotes_fresh"]
    assert quality["unavailable_symbols"] == ["SGOV"]

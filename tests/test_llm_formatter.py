"""Characterization tests for MarketDataFormatter pivot-level detection.

strategy/llm/ had no direct tests (Q-4 coverage gap). These pin the CURRENT
behavior of resistance/support detection and the rendered "Key Price Levels"
section so the N-1 refactor (merging the mirror-image _find_resistance_levels /
_find_support_levels into one helper) stays behavior-preserving. They record
"the output is currently this", not "this is correct" — the before/after green
safety net for the refactor.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.strategy.llm.data_formatter import MarketDataFormatter


@pytest.fixture
def engineered_bars() -> pd.DataFrame:
    """Bars with clear local peaks (high=15 at i=2) and troughs (low=6 at i=5).

    The pivot scan checks two neighbors on each side (range(2, len-2)), so the
    peak/trough must be strictly above/below the two bars on either side.
    """
    return pd.DataFrame(
        {
            "open": [10, 11, 12, 11, 10, 9, 8, 9, 10, 11, 12, 13],
            "high": [11, 12, 15, 12, 11, 10, 9, 11, 13, 12, 14, 13],
            "low": [9, 10, 11, 10, 8, 6, 7, 8, 9, 10, 11, 12],
            "close": [10, 11, 13, 11, 10, 8, 8, 10, 12, 11, 13, 12],
            "volume": [100, 120, 200, 90, 80, 300, 110, 130, 150, 90, 210, 140],
        }
    )


def test_find_resistance_levels_pins_current(engineered_bars):
    f = MarketDataFormatter(lookback_days=30)
    current = float(engineered_bars.iloc[-1]["close"])  # 12.0
    levels = f._find_resistance_levels(engineered_bars, current)
    # peaks above current price (12), ascending
    assert [float(x) for x in levels] == [15.0]


def test_find_support_levels_pins_current(engineered_bars):
    f = MarketDataFormatter(lookback_days=30)
    current = float(engineered_bars.iloc[-1]["close"])  # 12.0
    levels = f._find_support_levels(engineered_bars, current)
    # troughs below current price (12), descending
    assert [float(x) for x in levels] == [6.0]


def test_price_levels_section_pins_current(engineered_bars):
    """The rendered section (which consumes both helpers) must be unchanged."""
    f = MarketDataFormatter(lookback_days=30)
    section = f._format_price_levels(engineered_bars)
    assert section == (
        "## Key Price Levels\n"
        "Pivot Point: $11.00\n"
        "Resistance 1: $16.00 (+33.3%)\n"
        "Resistance 2: $20.00 (+66.7%)\n"
        "Support 1: $7.00 (-41.7%)\n"
        "Support 2: $2.00 (-83.3%)\n"
        "Recent Highs: $15.00\n"
        "Recent Lows: $6.00"
    )


def test_claude_default_model_is_current_not_stale():
    """N-3: the ClaudeClient fallback default must be the current id, not the old
    dated snapshot. Locks the value so a future model bump is a conscious edit."""
    from src.strategy.llm.client import ClaudeClient

    client = ClaudeClient(api_key="test-key")
    assert client.default_model == "claude-sonnet-4-6"
    assert client.default_model != "claude-sonnet-4-20250514"  # the retired stale id


def test_pivot_detection_handles_short_frames():
    """< 5 bars => the range(2, len-2) loop is empty => no levels (current behavior)."""
    f = MarketDataFormatter()
    bars = pd.DataFrame(
        {
            "open": [10, 11, 12],
            "high": [11, 12, 13],
            "low": [9, 10, 11],
            "close": [10, 11, 12],
            "volume": [100, 120, 140],
        }
    )
    assert f._find_resistance_levels(bars, 12.0) == []
    assert f._find_support_levels(bars, 12.0) == []

"""Unit tests for src.surge.detector — SurgeDetector."""

from datetime import date, datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.core.types import TimeFrame
from src.surge.detector import SurgeDetector
from src.surge.settings import SurgeDetectionConfig


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_provider(bars: dict | None = None):
    """Return a mock BaseDataProvider."""
    p = MagicMock()

    def _get_daily_bar(symbol: str, d: date):
        if bars is None:
            return None
        return bars.get(symbol)

    def _get_bars(symbol, timeframe=TimeFrame.DAY_1, start=None, end=None, limit=100):
        # Return enough rows for 20-day avg volume
        idx = pd.date_range(end=end or datetime.now(), periods=25, freq="B")
        return pd.DataFrame(
            {"open": 100.0, "high": 105.0, "low": 99.0, "close": 102.0, "volume": 5_000_000},
            index=idx,
        )

    p.get_daily_bar.side_effect = _get_daily_bar
    p.get_bars.side_effect = _get_bars
    return p


def _bar(close: float, prev_close: float, volume: int = 10_000_000) -> dict:
    return {
        "open": close - 1.0,
        "high": close + 2.0,
        "low": close - 2.0,
        "close": close,
        "volume": volume,
        "prev_close": prev_close,
    }


# ---------------------------------------------------------------------------
# _calculate_change
# ---------------------------------------------------------------------------

class TestCalculateChange:
    def test_positive(self):
        assert SurgeDetector._calculate_change(110.0, 100.0) == 10.0

    def test_negative(self):
        assert SurgeDetector._calculate_change(93.0, 100.0) == pytest.approx(-7.0)

    def test_zero(self):
        assert SurgeDetector._calculate_change(100.0, 100.0) == 0.0


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

class TestScan:
    def test_surge_detected(self):
        provider = _make_provider({"AAPL": _bar(110.0, 100.0)})
        detector = SurgeDetector(provider)
        records = detector.scan(["AAPL"], today=date(2026, 6, 3))
        assert len(records) == 1
        assert records[0].symbol == "AAPL"
        assert records[0].direction == "up"
        assert records[0].change_pct == 10.0

    def test_dive_detected(self):
        provider = _make_provider({"AAPL": _bar(93.0, 100.0)})
        detector = SurgeDetector(provider)
        records = detector.scan(["AAPL"], today=date(2026, 6, 3))
        assert len(records) == 1
        assert records[0].direction == "down"
        assert records[0].change_pct == -7.0

    def test_below_threshold_skipped(self):
        provider = _make_provider({"AAPL": _bar(105.0, 100.0)})  # +5%, < 7%
        detector = SurgeDetector(provider)
        records = detector.scan(["AAPL"], today=date(2026, 6, 3))
        assert len(records) == 0

    def test_custom_threshold(self):
        config = SurgeDetectionConfig(threshold_pct=3.0)
        provider = _make_provider({"AAPL": _bar(105.0, 100.0)})  # +5%, >= 3%
        detector = SurgeDetector(provider, config)
        records = detector.scan(["AAPL"], today=date(2026, 6, 3))
        assert len(records) == 1

    def test_no_data_skipped(self):
        provider = _make_provider({})  # no data for any symbol
        detector = SurgeDetector(provider)
        records = detector.scan(["AAPL"], today=date(2026, 6, 3))
        assert len(records) == 0

    def test_fail_isolation(self):
        """One failing symbol must not sink the whole scan."""
        provider = _make_provider({"AAPL": _bar(110.0, 100.0)})

        def _get_daily_bar(symbol, d):
            if symbol == "MSFT":
                raise RuntimeError("boom")
            return _bar(110.0, 100.0)

        provider.get_daily_bar.side_effect = _get_daily_bar
        detector = SurgeDetector(provider)
        records = detector.scan(["AAPL", "MSFT"], today=date(2026, 6, 3))
        # AAPL should be detected; MSFT error logged and skipped
        assert len(records) == 1
        assert records[0].symbol == "AAPL"

    def test_sorted_by_abs_change_desc(self):
        provider = _make_provider({
            "A": _bar(108.0, 100.0),   # +8%
            "B": _bar(115.0, 100.0),   # +15%
            "C": _bar(92.0, 100.0),    # -8%
        })
        detector = SurgeDetector(provider)
        records = detector.scan(["A", "B", "C"], today=date(2026, 6, 3))
        assert len(records) == 3
        assert records[0].symbol == "B"  # +15% largest abs
        assert abs(records[0].change_pct) == 15.0

    def test_no_prev_close_skipped(self):
        bar_no_prev = {"open": 110.0, "high": 112.0, "low": 108.0, "close": 110.0, "volume": 1_000_000}
        provider = _make_provider({"AAPL": bar_no_prev})
        detector = SurgeDetector(provider)
        records = detector.scan(["AAPL"], today=date(2026, 6, 3))
        assert len(records) == 0

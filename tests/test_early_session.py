"""Tests for early-session signal detection (F51).

Covers: records, config, buffer, detector, dumper, index_writer, monitor.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.early_session.buffer import BufferManager
from src.early_session.settings import EarlySessionConfig
from src.early_session.detector import SignalDetector
from src.early_session.dumper import WindowDumper
from src.early_session.index_writer import IndexWriter
from src.early_session.records import (
    BarRecord,
    EventIndex,
    SignalEvent,
    bar_from_jsonl,
    bar_to_jsonl,
    event_index_from_jsonl,
    event_index_to_jsonl,
)

UTC = timezone.utc

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_bar(symbol="AAPL", minute=30, close=100.0, ts_date=None):
    """Create a BarRecord with a fixed timestamp."""
    d = ts_date or datetime(2026, 6, 4, 9, minute, 0, tzinfo=UTC)
    return BarRecord(
        timestamp=d, symbol=symbol, open=close - 0.5, high=close + 0.5,
        low=close - 1.0, close=close, volume=1000.0,
    )


def _make_bars(symbol="AAPL", closes=None):
    """Create a list of BarRecords from a list of close prices."""
    return [
        _make_bar(symbol=symbol, minute=30 + i, close=c)
        for i, c in enumerate(closes or [])
    ]


# ---------------------------------------------------------------------------
# BarRecord / JSONL serialization
# ---------------------------------------------------------------------------


class TestBarRecord:
    def test_round_trip(self):
        bar = _make_bar(close=195.5)
        line = bar_to_jsonl(bar)
        bar2 = bar_from_jsonl(line, "AAPL")
        assert bar2.symbol == "AAPL"
        assert bar2.close == 195.5
        assert bar2.open == 195.0

    def test_jsonl_keys(self):
        bar = _make_bar(close=100.0)
        line = bar_to_jsonl(bar)
        d = json.loads(line)
        assert set(d.keys()) == {"t", "o", "h", "l", "c", "v"}

    def test_vwap_included_when_present(self):
        bar = _make_bar(close=100.0)
        bar.vwap = 99.8
        line = bar_to_jsonl(bar)
        d = json.loads(line)
        assert "vw" in d
        assert d["vw"] == 99.8


class TestEventIndex:
    def test_round_trip(self):
        ei = EventIndex(
            symbol="AAPL", date="2026-06-04", detected_at="2026-06-04T09:35:00Z",
            direction="drop", trigger_pct=-5.2, trigger_window_min=10,
            open=195.0, prev_close=196.0, gap_pct=-0.51,
            data_file="2026-06-04/AAPL_093500_drop.jsonl", bar_count=60,
            time_range_start="2026-06-04T09:20:00Z",
            time_range_end="2026-06-04T10:20:00Z",
        )
        line = event_index_to_jsonl(ei)
        ei2 = event_index_from_jsonl(line)
        assert ei2.symbol == "AAPL"
        assert ei2.trigger_pct == -5.2
        assert ei2.bar_count == 60


# ---------------------------------------------------------------------------
# Hypothesis PBT (serialization round-trip)
# ---------------------------------------------------------------------------

try:
    from hypothesis import given, settings
    from hypothesis.strategies import floats, integers, text, datetimes, booleans

    @given(
        symbol=text(min_size=1, max_size=5, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        close=floats(min_value=0.01, max_value=10000.0),
        volume=floats(min_value=0, max_value=1e9),
    )
    @settings(max_examples=100)
    def test_bar_round_trip_pbt(symbol, close, volume):
        bar = BarRecord(
            timestamp=datetime(2026, 6, 4, 9, 30, tzinfo=UTC),
            symbol=symbol, open=close, high=close, low=close,
            close=close, volume=volume,
        )
        line = bar_to_jsonl(bar)
        bar2 = bar_from_jsonl(line, symbol)
        assert bar2.close == close
        assert bar2.volume == volume

except ImportError:
    pass  # Hypothesis not available


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestEarlySessionConfig:
    def test_defaults(self):
        c = EarlySessionConfig()
        assert c.threshold_pct == 5.0
        assert c.window_minutes == 10
        assert c.enabled is True

    def test_from_settings_empty(self):
        c = EarlySessionConfig.from_settings({})
        assert c.threshold_pct == 5.0

    def test_from_settings_override(self):
        c = EarlySessionConfig.from_settings({
            "early_session": {"threshold_pct": 3.0, "window_minutes": 5}
        })
        assert c.threshold_pct == 3.0
        assert c.window_minutes == 5

    def test_unknown_keys_ignored(self):
        c = EarlySessionConfig.from_settings({
            "early_session": {"threshold_pct": 4.0, "bogus_key": 999}
        })
        assert c.threshold_pct == 4.0


# ---------------------------------------------------------------------------
# BufferManager
# ---------------------------------------------------------------------------


class TestBufferManager:
    def test_push_and_get_window(self):
        bm = BufferManager(retention_minutes=20)
        bar = _make_bar(minute=30, close=100.0)
        bm.push("AAPL", bar)
        assert len(bm.get_window("AAPL", 5)) == 1

    def test_retention_eviction(self):
        bm = BufferManager(retention_minutes=5)
        old = datetime(2026, 6, 4, 9, 20, tzinfo=UTC)
        bm.push("AAPL", _make_bar(minute=20, close=100.0, ts_date=old))
        recent = _make_bar(minute=31, close=101.0)
        bm.push("AAPL", recent)
        bars = bm.get_window("AAPL", 20)
        # The old bar should be evicted (retention=5 min, old is at 9:20, now's recent is 9:31)
        assert any(b.close == 101.0 for b in bars)
        # old bar at 9:20 should be evicted if retention=5 means bars more than 5 min old
        # Actually retention eviction triggers on push with the argument's timestamp
        # Since retention=5, bars older than recent.timestamp - 5min = 9:26 are evicted
        # Old bar at 9:20 is older → evicted
        assert not any(b.close == 100.0 for b in bars)

    def test_get_range(self):
        bm = BufferManager(retention_minutes=20)
        for i in range(10):
            bm.push("AAPL", _make_bar(minute=30 + i, close=float(100 + i)))
        bars = bm.get_range(
            "AAPL",
            datetime(2026, 6, 4, 9, 33, tzinfo=UTC),
            datetime(2026, 6, 4, 9, 35, tzinfo=UTC),
        )
        closes = {b.close for b in bars}
        assert 103.0 in closes
        assert 104.0 in closes
        assert 105.0 in closes

    def test_clear(self):
        bm = BufferManager(retention_minutes=20)
        bm.push("AAPL", _make_bar())
        bm.clear("AAPL")
        assert bm.get_window("AAPL", 5) == []

    def test_unknown_symbol(self):
        bm = BufferManager(retention_minutes=20)
        assert bm.get_window("NOPE", 5) == []
        assert bm.get_range("NOPE", datetime.now(UTC), datetime.now(UTC)) == []


# ---------------------------------------------------------------------------
# SignalDetector
# ---------------------------------------------------------------------------


class TestSignalDetector:
    def test_drop_detected(self):
        sd = SignalDetector(threshold_pct=5.0, window_minutes=5)
        closes = [200.0, 198.0, 196.0, 194.0, 188.0]  # -6%
        event = sd.detect(_make_bars(closes=closes))
        assert event is not None
        assert event.direction == "drop"
        assert event.trigger_pct < -5.0

    def test_surge_detected(self):
        sd = SignalDetector(threshold_pct=5.0, window_minutes=5)
        closes = [100.0, 102.0, 104.0, 106.0, 108.0]  # +8%
        event = sd.detect(_make_bars(closes=closes))
        assert event is not None
        assert event.direction == "surge"
        assert event.trigger_pct > 5.0

    def test_no_trigger_below_threshold(self):
        sd = SignalDetector(threshold_pct=5.0, window_minutes=5)
        closes = [100.0, 101.0, 102.0, 103.0, 104.0]  # +4%
        assert sd.detect(_make_bars(closes=closes)) is None

    def test_insufficient_bars(self):
        sd = SignalDetector(threshold_pct=5.0, window_minutes=10)
        assert sd.detect(_make_bars(closes=[100.0, 98.0])) is None

    def test_zero_first_close(self):
        sd = SignalDetector(threshold_pct=5.0, window_minutes=5)
        closes = [0.0, 100.0, 100.0, 100.0, 100.0]
        assert sd.detect(_make_bars(closes=closes)) is None


# ---------------------------------------------------------------------------
# Hypothesis PBT — detector invariants
# ---------------------------------------------------------------------------

try:
    from hypothesis import given, settings as hp_settings
    from hypothesis.strategies import floats, integers, lists

    @given(
        closes=lists(
            floats(min_value=1.0, max_value=1000.0),
            min_size=1, max_size=30,
        ),
        threshold=floats(min_value=0.5, max_value=20.0),
        window=integers(min_value=1, max_value=30),
    )
    @hp_settings(max_examples=200)
    def test_detector_invariants_pbt(closes, threshold, window):
        """Property: detect() either returns None or a valid SignalEvent."""
        sd = SignalDetector(threshold_pct=threshold, window_minutes=window)
        bars = _make_bars(closes=closes)
        event = sd.detect(bars)
        if event is None:
            return  # valid
        # If an event is returned, checks:
        assert event.direction in ("surge", "drop")
        assert abs(event.trigger_pct) >= threshold
        if event.direction == "surge":
            assert event.trigger_pct > 0
        else:
            assert event.trigger_pct < 0
        assert event.symbol == "AAPL"

except ImportError:
    pass


# ---------------------------------------------------------------------------
# WindowDumper
# ---------------------------------------------------------------------------


class TestWindowDumper:
    def test_write_before(self, tmp_path):
        dumper = WindowDumper(tmp_path / "workspace")
        bar = _make_bar(minute=30, close=195.0)
        event = SignalEvent(
            symbol="AAPL", date=datetime(2026, 6, 4).date(),
            detected_at=datetime(2026, 6, 4, 9, 35, tzinfo=UTC),
            direction="drop", trigger_pct=-5.5, trigger_window_min=10,
            open=200.0, prev_close=201.0, gap_pct=-0.5,
        )
        path = dumper.write_before(event, [bar])
        assert path.exists()
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 1
        d = json.loads(lines[0])
        assert d["c"] == 195.0

    def test_write_before_and_after(self, tmp_path):
        dumper = WindowDumper(tmp_path / "workspace")
        event = SignalEvent(
            symbol="TSLA", date=datetime(2026, 6, 4).date(),
            detected_at=datetime(2026, 6, 4, 9, 40, tzinfo=UTC),
            direction="surge", trigger_pct=6.0, trigger_window_min=10,
            open=250.0, prev_close=248.0, gap_pct=0.81,
        )
        before = [_make_bar(symbol="TSLA", minute=30 + i, close=float(250 + i)) for i in range(5)]
        after = [_make_bar(symbol="TSLA", minute=40 + i, close=float(260 + i)) for i in range(5)]

        p1 = dumper.write_before(event, before)
        p2 = dumper.write_after(event, after)
        assert p1 == p2
        lines = p1.read_text().strip().splitlines()
        assert len(lines) == 10


# ---------------------------------------------------------------------------
# IndexWriter
# ---------------------------------------------------------------------------


class TestIndexWriter:
    def test_append_and_read(self, tmp_path):
        writer = IndexWriter(tmp_path / "workspace")
        event = SignalEvent(
            symbol="AAPL", date=datetime(2026, 6, 4).date(),
            detected_at=datetime(2026, 6, 4, 9, 35, tzinfo=UTC),
            direction="drop", trigger_pct=-5.2, trigger_window_min=10,
            open=200.0, prev_close=201.0, gap_pct=-0.5,
        )
        data_file = Path("2026-06-04/AAPL_093500_drop.jsonl")
        writer.append(
            event, data_file, bar_count=60,
            time_start=datetime(2026, 6, 4, 9, 20, tzinfo=UTC),
            time_end=datetime(2026, 6, 4, 10, 20, tzinfo=UTC),
        )
        detected = writer.read_detected("2026-06-04")
        assert "AAPL" in detected

    def test_read_empty(self, tmp_path):
        writer = IndexWriter(tmp_path / "workspace")
        assert writer.read_detected("2026-06-04") == set()

    def test_multiple_appends(self, tmp_path):
        writer = IndexWriter(tmp_path / "workspace")
        for sym in ["AAPL", "TSLA", "MSFT"]:
            event = SignalEvent(
                symbol=sym, date=datetime(2026, 6, 4).date(),
                detected_at=datetime(2026, 6, 4, 9, 35, tzinfo=UTC),
                direction="drop", trigger_pct=-5.0, trigger_window_min=10,
                open=100.0, prev_close=101.0, gap_pct=-1.0,
            )
            writer.append(
                event, Path(f"2026-06-04/{sym}_093500_drop.jsonl"), bar_count=60,
                time_start=datetime(2026, 6, 4, 9, 20, tzinfo=UTC),
                time_end=datetime(2026, 6, 4, 10, 20, tzinfo=UTC),
            )
        detected = writer.read_detected("2026-06-04")
        assert detected == {"AAPL", "TSLA", "MSFT"}

    def test_idempotent_symbol_dedup(self, tmp_path):
        """Reading the index returns unique symbols even after restart."""
        writer = IndexWriter(tmp_path / "workspace")
        event = SignalEvent(
            symbol="AAPL", date=datetime(2026, 6, 4).date(),
            detected_at=datetime(2026, 6, 4, 9, 35, tzinfo=UTC),
            direction="drop", trigger_pct=-5.2, trigger_window_min=10,
            open=200.0, prev_close=201.0, gap_pct=-0.5,
        )
        writer.append(
            event, Path("f.jsonl"), bar_count=60,
            time_start=datetime(2026, 6, 4, 9, 20, tzinfo=UTC),
            time_end=datetime(2026, 6, 4, 10, 20, tzinfo=UTC),
        )
        # Simulate restart — re-read
        writer2 = IndexWriter(tmp_path / "workspace")
        detected2 = writer2.read_detected("2026-06-04")
        assert "AAPL" in detected2


# ---------------------------------------------------------------------------
# EarlySessionMonitor (integration)
# ---------------------------------------------------------------------------


class TestEarlySessionMonitor:
    def test_tick_no_signals(self, tmp_path):
        """Monitor tick runs cleanly when no signals trigger."""
        from src.early_session.monitor import EarlySessionMonitor

        config = EarlySessionConfig(
            enabled=True,
            threshold_pct=500.0,  # impossible threshold → no signals
            window_minutes=10,
            poll_interval_seconds=30,
        )

        # Mock data provider that returns flat bars
        mock_provider = MagicMock()
        mock_provider._symbols = ["AAPL", "TSLA"]

        def _mock_bars(symbols, timeframe=None, limit=None):
            import pandas as pd
            now = datetime(2026, 6, 4, 9, 35, tzinfo=UTC)
            result = {}
            for sym in symbols:
                df = pd.DataFrame({
                    "open": [100.0, 100.1],
                    "high": [100.5, 100.6],
                    "low": [99.5, 99.6],
                    "close": [100.0, 100.1],
                    "volume": [1000, 1000],
                }, index=[now, now + timedelta(minutes=1)])
                result[sym] = df
            return result

        mock_provider.get_bars.side_effect = _mock_bars

        monitor = EarlySessionMonitor(config, mock_provider, tmp_path / "workspace")
        monitor.start()
        # Force time to be within monitoring window
        monitor._monitor_end = datetime(2026, 6, 4, 10, 30, tzinfo=UTC)
        monitor.tick()

        # No events should be detected (threshold impossible)
        assert len(monitor._detected_today) == 0

    def test_signal_detection_and_dump(self, tmp_path):
        """Full tick cycle: detect a drop → dump → index."""
        from src.early_session.monitor import EarlySessionMonitor

        config = EarlySessionConfig(
            enabled=True,
            threshold_pct=5.0,
            window_minutes=5,
            dump_before_minutes=5,
            dump_after_minutes=0,  # immediate finalize
            poll_interval_seconds=30,
        )

        mock_provider = MagicMock()
        mock_provider._symbols = ["AAPL"]

        now = datetime(2026, 6, 4, 9, 35, tzinfo=UTC)

        def _mock_bars(symbols, timeframe=None, limit=None):
            result = {}
            for sym in symbols:
                # Generate 6 bars — last close is 188.0 (-6% from first 200.0)
                closes = [200.0, 198.0, 196.0, 194.0, 192.0, 188.0]
                df = pd.DataFrame({
                    "open": [c + 0.5 for c in closes],
                    "high": [c + 1.0 for c in closes],
                    "low": [c - 1.0 for c in closes],
                    "close": closes,
                    "volume": [1000] * len(closes),
                }, index=[now + timedelta(minutes=i - len(closes) + 1) for i in range(len(closes))])
                result[sym] = df
            return result

        mock_provider.get_bars.side_effect = _mock_bars

        monitor = EarlySessionMonitor(config, mock_provider, tmp_path / "workspace")
        monitor.start()
        monitor._monitor_end = datetime(2026, 6, 4, 10, 30, tzinfo=UTC)
        monitor.tick()

        # Check that the event was detected and files were created
        assert "AAPL" in monitor._detected_today

        # Check dump files exist
        date_dir = tmp_path / "workspace" / "early_session" / "2026-06-04"
        assert date_dir.exists()
        jsonl_files = list(date_dir.glob("*.jsonl"))
        assert len(jsonl_files) > 0

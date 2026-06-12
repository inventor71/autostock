"""F56 — regression tests for the bugs found in the post-merge code review.

Covers:
- C-1 (FR-1): BaseDataProvider.get_daily_bar resolves prev_close (was always None).
- C-3 (FR-3): DecisionExecutor cursor advances past dedup-superseded decisions,
  holds before retryable ones, and never re-executes terminal ones.
- C-2 (FR-2): EarlySessionMonitor uses ET (America/New_York) for monitor_end.
- C-4 (FR-4): finalize uses the SignalEvent captured at detection (no None crash).
- C-5 (FR-5): effective buffer retention covers the whole dump window.
- C-6 (FR-6): universe is resolvable via injected list/callable.
- PBT (Partial): _calculate_change + EventIndex JSONL round-trip.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from unittest.mock import MagicMock

from src.core.types import TimeFrame
from src.data.base import BaseDataProvider

_ET = ZoneInfo("America/New_York")


# ===========================================================================
# C-1 (FR-1) — get_daily_bar prev_close
# ===========================================================================


class _DailyProvider(BaseDataProvider):
    """Minimal provider returning a fixed multi-day daily DataFrame."""

    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_bars(self, symbol, timeframe=TimeFrame.DAY_1, start=None, end=None, limit=100):
        return self._df

    def get_latest_price(self, symbol):
        return float(self._df.iloc[-1]["close"])


def _daily_df(dates_closes: list[tuple[str, float]]) -> pd.DataFrame:
    idx = pd.to_datetime([d for d, _ in dates_closes])
    closes = [c for _, c in dates_closes]
    return pd.DataFrame(
        {
            "open": [c - 1 for c in closes],
            "high": [c + 1 for c in closes],
            "low": [c - 2 for c in closes],
            "close": closes,
            "volume": [1_000_000] * len(closes),
        },
        index=idx,
    )


class TestGetDailyBar:
    def test_prev_close_resolved(self):
        df = _daily_df([("2026-06-01", 100.0), ("2026-06-02", 102.0), ("2026-06-03", 110.0)])
        bar = _DailyProvider(df).get_daily_bar("AAPL", date(2026, 6, 3))
        assert bar is not None
        assert bar["close"] == 110.0
        assert bar["prev_close"] == 102.0  # 06-02 close — the bug returned None

    def test_target_day_in_middle(self):
        # Even if later rows exist, the row for d is "today" and d-1 is prev.
        df = _daily_df([("2026-06-01", 100.0), ("2026-06-02", 102.0), ("2026-06-03", 110.0)])
        bar = _DailyProvider(df).get_daily_bar("AAPL", date(2026, 6, 2))
        assert bar["close"] == 102.0
        assert bar["prev_close"] == 100.0

    def test_no_prev_when_single_bar(self):
        df = _daily_df([("2026-06-03", 110.0)])
        bar = _DailyProvider(df).get_daily_bar("AAPL", date(2026, 6, 3))
        assert bar["prev_close"] is None

    def test_empty_returns_none(self):
        df = _daily_df([]).iloc[0:0]
        assert _DailyProvider(df).get_daily_bar("AAPL", date(2026, 6, 3)) is None

    def test_surge_detector_now_produces_record(self):
        # End-to-end: with prev_close resolvable, SurgeDetector emits a record.
        from src.surge.detector import SurgeDetector
        from src.surge.settings import SurgeDetectionConfig

        df = _daily_df([("2026-06-02", 100.0), ("2026-06-03", 110.0)])  # +10%
        detector = SurgeDetector(_DailyProvider(df), SurgeDetectionConfig(threshold_pct=7.0))
        records = detector.scan(["AAPL"], today=date(2026, 6, 3))
        assert len(records) == 1
        assert records[0].symbol == "AAPL"
        assert records[0].direction == "up"
        assert records[0].change_pct == 10.0


# ===========================================================================
# C-3 (FR-3) — executor cursor advancement
# ===========================================================================


def _executor(tmp_path):
    from src.agent.journal import Journal
    from src.agent.executor import DecisionExecutor
    from src.execution.brokers.simulated_broker import SimulatedBroker
    from src.risk.manager import RiskManager

    broker = SimulatedBroker(initial_capital=100_000.0)
    rm = RiskManager(max_position_pct=0.5, use_bracket_orders=True)
    provider = MagicMock()
    journal = Journal(root=tmp_path / "ws")
    ex = DecisionExecutor(broker, rm, provider, journal=journal, universe=["AAPL", "MSFT"])
    return ex, journal


class TestExecutorCursor:
    def test_advances_past_superseded(self, tmp_path, monkeypatch):
        from src.agent.journal import Decision
        from src.agent.executor import ExecutionOutcome

        ex, journal = _executor(tmp_path)
        journal.append_decision(Decision(symbol="AAPL", action="HOLD"))   # idx0 superseded
        journal.append_decision(Decision(symbol="AAPL", action="HOLD"))   # idx1 latest
        monkeypatch.setattr(
            ex, "execute_decision",
            lambda d, decision_index=-1: ExecutionOutcome(d, "skipped_hold", ""),
        )
        ex.execute_pending()
        cursor, terminal = ex._load_cursor()
        # Bug: cursor stalled at 0 because idx0 (superseded) never became terminal.
        assert cursor == 2
        assert 0 in terminal and 1 in terminal

    def test_holds_before_retryable(self, tmp_path, monkeypatch):
        from src.agent.journal import Decision
        from src.agent.executor import ExecutionOutcome

        ex, journal = _executor(tmp_path)
        journal.append_decision(Decision(symbol="AAPL", action="BUY"))   # idx0 → error
        journal.append_decision(Decision(symbol="MSFT", action="BUY"))   # idx1 → executed

        def fake(d, decision_index=-1):
            status = "error" if d.symbol == "AAPL" else "executed"
            return ExecutionOutcome(d, status, "")

        monkeypatch.setattr(ex, "execute_decision", fake)
        ex.execute_pending()
        cursor, terminal = ex._load_cursor()
        assert cursor == 0          # stops before the retryable (error) decision
        assert 1 in terminal        # executed MSFT is terminal
        assert 0 not in terminal

    def test_terminal_not_reexecuted(self, tmp_path, monkeypatch):
        from src.agent.journal import Decision
        from src.agent.executor import ExecutionOutcome

        ex, journal = _executor(tmp_path)
        journal.append_decision(Decision(symbol="AAPL", action="BUY"))
        calls: list[int] = []

        def fake(d, decision_index=-1):
            calls.append(decision_index)
            return ExecutionOutcome(d, "executed", "")

        monkeypatch.setattr(ex, "execute_decision", fake)
        ex.execute_pending()
        ex.execute_pending()  # second cycle must not re-run idx0
        assert calls == [0]


# ===========================================================================
# C-2 / C-4 / C-5 / C-6 — EarlySessionMonitor
# ===========================================================================


class TestEarlySessionMonitor:
    def _monitor(self, tmp_path, **cfg_kw):
        from src.early_session.settings import EarlySessionConfig
        from src.early_session.monitor import EarlySessionMonitor

        cfg = EarlySessionConfig(**cfg_kw)
        provider = MagicMock()
        provider.get_bars.return_value = {}
        return EarlySessionMonitor(cfg, provider, tmp_path / "ws", symbols=["AAPL"]), cfg

    def test_monitor_end_is_et(self, tmp_path):
        monitor, _ = self._monitor(tmp_path, monitor_end_et="10:30")
        monitor.start()
        assert monitor._monitor_end is not None
        assert monitor._monitor_end.tzinfo == _ET
        assert (monitor._monitor_end.hour, monitor._monitor_end.minute) == (10, 30)
        # monitor_end is today's ET date (not a UTC-misinterpreted instant).
        assert monitor._monitor_end.date() == datetime.now(_ET).date()

    def test_effective_retention_covers_dump_window(self, tmp_path):
        monitor, cfg = self._monitor(
            tmp_path,
            buffer_retention_minutes=20,
            dump_before_minutes=15,
            dump_after_minutes=45,
            window_minutes=10,
        )
        assert cfg.effective_retention_minutes == 15 + 45 + 10 + 5  # 75
        assert monitor._buffer._retention_minutes == 75

    def test_finalize_uses_stored_event(self, tmp_path):
        from src.early_session.records import SignalEvent

        monitor, _ = self._monitor(
            tmp_path, dump_before_minutes=5, dump_after_minutes=0, window_minutes=5
        )
        monitor._running = True
        ev = SignalEvent(
            symbol="AAPL", date=date(2026, 6, 4),
            detected_at=datetime(2026, 6, 4, 9, 35, tzinfo=_ET),
            direction="drop", trigger_pct=-6.0, trigger_window_min=5,
            open=200.0, prev_close=210.0, gap_pct=-4.76,
        )
        # Detection normally writes the before-window first; mirror that so the
        # event file exists for the append in finalize.
        monitor._dumper.write_before(ev, [])
        # finalize_at in the past → finalize fires this tick. The old code lost the
        # event and re-detected an empty window → None → AttributeError.
        monitor._pending_finalizes["AAPL"] = (ev, datetime(2000, 1, 1, tzinfo=_ET))
        monitor.tick()  # must not raise
        assert "AAPL" not in monitor._pending_finalizes
        idx = tmp_path / "ws" / "early_session" / "2026-06-04" / "_index.jsonl"
        assert idx.exists()

    def test_symbols_injection(self, tmp_path):
        from src.early_session.settings import EarlySessionConfig
        from src.early_session.monitor import EarlySessionMonitor

        m_list = EarlySessionMonitor(EarlySessionConfig(), MagicMock(), tmp_path / "a", symbols=["NVDA"])
        assert m_list._symbols() == ["NVDA"]
        m_call = EarlySessionMonitor(
            EarlySessionConfig(), MagicMock(), tmp_path / "b", symbols=lambda: ["AMD", "INTC"]
        )
        assert m_call._symbols() == ["AMD", "INTC"]


# ===========================================================================
# PBT (Partial) — pure functions + serialization round-trip
# ===========================================================================


class TestPropertyBased:
    def test_calculate_change_pbt(self):
        from hypothesis import given
        from hypothesis.strategies import floats
        from src.surge.detector import SurgeDetector

        @given(
            prev=floats(min_value=0.01, max_value=1e6, allow_nan=False, allow_infinity=False),
            today=floats(min_value=0.01, max_value=1e6, allow_nan=False, allow_infinity=False),
        )
        def _prop(prev, today):
            change = SurgeDetector._calculate_change(today, prev)
            # sign of change matches direction of move
            if today > prev:
                assert change > 0
            elif today < prev:
                assert change < 0
            else:
                assert change == 0
            # algebraic identity
            assert change == pytest.approx((today - prev) / prev * 100)

        _prop()

    def test_event_index_round_trip_pbt(self):
        from hypothesis import given
        from hypothesis.strategies import floats, integers, sampled_from, text
        from src.early_session.records import (
            EventIndex,
            event_index_from_jsonl,
            event_index_to_jsonl,
        )

        finite = floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6)

        @given(
            symbol=text(min_size=1, max_size=6),
            direction=sampled_from(["surge", "drop"]),
            trigger_pct=finite,
            window=integers(min_value=1, max_value=120),
            open_=finite, prev_close=finite, gap=finite,
            bar_count=integers(min_value=0, max_value=10_000),
        )
        def _prop(symbol, direction, trigger_pct, window, open_, prev_close, gap, bar_count):
            rec = EventIndex(
                symbol=symbol, date="2026-06-04", detected_at="2026-06-04T09:35:00",
                direction=direction, trigger_pct=trigger_pct, trigger_window_min=window,
                open=open_, prev_close=prev_close, gap_pct=gap,
                data_file="AAPL_093500_drop.jsonl", bar_count=bar_count,
                time_range_start="2026-06-04T09:20:00", time_range_end="2026-06-04T10:20:00",
            )
            rt = event_index_from_jsonl(event_index_to_jsonl(rec))
            assert rt == rec

        _prop()

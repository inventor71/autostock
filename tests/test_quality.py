"""Tests for the Decision Quality Metrics module (F24)."""

from __future__ import annotations

from datetime import datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.agent.journal import Decision
from src.agent.quality.aggregate import rolling, summary
from src.agent.quality.metrics import (
    confidence_calibration,
    direction_hit_rate,
    exit_timing,
    mae,
    mfe,
    realized_rr,
    stop_quality,
    target_quality,
)
from src.agent.quality.models import DecisionOutcome, OHLC, RoundTrip
from src.agent.quality.snapshot import quality_snapshot


def _ohlc(date: str, o: float, h: float, l: float, c: float) -> OHLC:
    return OHLC(date=date, open=o, high=h, low=l, close=c)


def _buy_decision(symbol="AAPL", confidence=0.8, stop=90.0, target=120.0, limit=100.0):
    return Decision(
        ts=datetime(2026, 1, 5),
        symbol=symbol,
        action="BUY",
        confidence=confidence,
        stop=stop,
        target=target,
        limit=limit,
    )


def _sell_decision(symbol="AAPL"):
    return Decision(
        ts=datetime(2026, 1, 10),
        symbol=symbol,
        action="SELL",
        confidence=0.7,
    )


def _round_trip(entry=100.0, exit_=110.0):
    return RoundTrip(
        symbol="AAPL",
        qty=10,
        entry_price=entry,
        exit_price=exit_,
        opened_at="2026-01-05",
        closed_at="2026-01-12",
        realized_pnl=(exit_ - entry) * 10,
        return_pct=((exit_ / entry) - 1) * 100,
    )


def _price_path_up():
    return [
        _ohlc("2026-01-05", 100, 102, 98, 101),
        _ohlc("2026-01-06", 101, 105, 100, 104),
        _ohlc("2026-01-07", 104, 108, 103, 107),
        _ohlc("2026-01-08", 107, 112, 106, 110),
        _ohlc("2026-01-09", 110, 115, 109, 113),
    ]


def _price_path_down():
    return [
        _ohlc("2026-01-05", 100, 102, 98, 99),
        _ohlc("2026-01-06", 99, 100, 93, 94),
        _ohlc("2026-01-07", 94, 95, 88, 89),
        _ohlc("2026-01-08", 89, 91, 85, 86),
        _ohlc("2026-01-09", 86, 88, 83, 84),
    ]


def _outcome_up():
    return DecisionOutcome(
        decision=_buy_decision(),
        round_trip=_round_trip(),
        price_path=_price_path_up(),
        match_method="execution_log",
    )


def _outcome_down():
    return DecisionOutcome(
        decision=_buy_decision(stop=95.0),
        round_trip=_round_trip(entry=100.0, exit_=86.0),
        price_path=_price_path_down(),
        match_method="execution_log",
    )


# ── Direction hit rate ──


class TestDirectionHitRate:
    def test_all_hits(self):
        result = direction_hit_rate([_outcome_up(), _outcome_up()])
        assert result["rate"] == 1.0
        assert result["total"] == 2

    def test_no_hits(self):
        result = direction_hit_rate([_outcome_down()])
        assert result["rate"] == 0.0

    def test_empty(self):
        result = direction_hit_rate([])
        assert result["total"] == 0

    def test_sell_excluded(self):
        sell_outcome = DecisionOutcome(
            decision=_sell_decision(), price_path=_price_path_up()
        )
        result = direction_hit_rate([sell_outcome])
        assert result["total"] == 0


# ── MAE / MFE ──


class TestMAEMFE:
    def test_mae_positive(self):
        result = mae(_outcome_up())
        assert result is not None
        assert result == pytest.approx((100 - 98) / 100, abs=0.001)

    def test_mfe_positive(self):
        result = mfe(_outcome_up())
        assert result is not None
        assert result == pytest.approx((115 - 100) / 100, abs=0.001)

    def test_mae_none_without_round_trip(self):
        o = DecisionOutcome(decision=_buy_decision(), price_path=_price_path_up())
        assert mae(o) is None

    def test_mfe_none_without_price_path(self):
        o = DecisionOutcome(decision=_buy_decision(), round_trip=_round_trip())
        assert mfe(o) is None


@given(
    entry=st.floats(min_value=1.0, max_value=1000.0),
    low=st.floats(min_value=0.5, max_value=999.0),
    high=st.floats(min_value=1.0, max_value=1500.0),
)
@settings(max_examples=50)
def test_mae_mfe_range_invariant(entry, low, high):
    """MAE >= 0, MFE >= 0 for any valid price path."""
    if low > entry:
        low = entry
    if high < entry:
        high = entry
    pp = [_ohlc("2026-01-05", entry, high, low, entry)]
    rt = _round_trip(entry=entry, exit_=entry)
    o = DecisionOutcome(
        decision=_buy_decision(),
        round_trip=rt,
        price_path=pp,
        match_method="execution_log",
    )
    m = mae(o)
    f = mfe(o)
    assert m is not None and m >= 0
    assert f is not None and f >= 0


# ── Stop quality ──


class TestStopQuality:
    def test_appropriate(self):
        result = stop_quality(_outcome_down())
        assert result == "appropriate"

    def test_no_stop(self):
        o = DecisionOutcome(
            decision=_buy_decision(stop=None),
            price_path=_price_path_up(),
        )
        assert stop_quality(o) == "n/a"

    def test_noise_hit(self):
        path = [
            _ohlc("2026-01-05", 100, 102, 94, 95),
            _ohlc("2026-01-06", 95, 105, 94, 104),
            _ohlc("2026-01-07", 104, 110, 103, 108),
        ]
        o = DecisionOutcome(
            decision=_buy_decision(stop=95.0),
            price_path=path,
            match_method="execution_log",
        )
        result = stop_quality(o)
        assert result == "noise_hit"


# ── Target quality ──


class TestTargetQuality:
    def test_reached(self):
        o = DecisionOutcome(
            decision=_buy_decision(target=112.0),
            price_path=_price_path_up(),
        )
        result = target_quality(o)
        assert result["reached"] is True

    def test_not_reached(self):
        o = DecisionOutcome(
            decision=_buy_decision(target=200.0),
            price_path=_price_path_up(),
        )
        result = target_quality(o)
        assert result["reached"] is False


# ── Confidence calibration ──


class TestConfidenceCalibration:
    def test_excludes_default_05(self):
        o = DecisionOutcome(
            decision=_buy_decision(confidence=0.5),
            price_path=_price_path_up(),
        )
        result = confidence_calibration([o])
        total = sum(v["count"] for v in result.values())
        assert total == 0

    def test_excludes_none(self):
        o = DecisionOutcome(
            decision=_buy_decision(confidence=None),
            price_path=_price_path_up(),
        )
        result = confidence_calibration([o])
        total = sum(v["count"] for v in result.values())
        assert total == 0

    def test_scored(self):
        o = DecisionOutcome(
            decision=_buy_decision(confidence=0.8),
            price_path=_price_path_up(),
        )
        result = confidence_calibration([o])
        assert result["0.7-0.9"]["count"] == 1


# ── Realized R:R ──


class TestRealizedRR:
    def test_positive_rr(self):
        o = _outcome_up()
        result = realized_rr(o)
        assert result is not None
        assert result > 0

    def test_none_without_stop(self):
        o = DecisionOutcome(
            decision=_buy_decision(stop=None),
            round_trip=_round_trip(),
        )
        assert realized_rr(o) is None


# ── Exit timing ──


class TestExitTiming:
    def test_sell_timing(self):
        o = DecisionOutcome(
            decision=_sell_decision(),
            price_path=_price_path_up(),
        )
        result = exit_timing(o)
        assert result is not None
        assert result > 0  # price went up after sell → opportunity cost

    def test_buy_returns_none(self):
        assert exit_timing(_outcome_up()) is None


# ── Aggregate ──


class TestAggregate:
    def test_summary_basic(self):
        outcomes = [_outcome_up(), _outcome_down()]
        s = summary(outcomes)
        assert s["total_outcomes"] == 2
        assert s["direction_hit_rate"]["total"] == 2

    def test_summary_empty(self):
        s = summary([])
        assert s["total_outcomes"] == 0

    def test_rolling_insufficient(self):
        outcomes = [_outcome_up()] * 5
        result = rolling(outcomes, window=20)
        assert result == []

    def test_rolling_sufficient(self):
        outcomes = [_outcome_up()] * 25
        result = rolling(outcomes, window=20)
        assert len(result) == 6


# ── Snapshot ──


class TestSnapshot:
    def test_none_below_min(self):
        outcomes = [_outcome_up()] * 3
        assert quality_snapshot(outcomes, min_decisions=5) is None

    def test_returns_string_above_min(self):
        outcomes = [_outcome_up()] * 6
        result = quality_snapshot(outcomes, min_decisions=5)
        assert result is not None
        assert "Direction hit rate" in result


# ── Prompts integration ──


class TestPromptsIntegration:
    def test_eod_prompt_without_quality(self):
        from src.agent.prompts import eod_review_prompt
        result = eod_review_prompt(outcomes=["AAPL BUY"])
        assert "Decision Quality Metrics" not in result

    def test_eod_prompt_with_quality(self):
        from src.agent.prompts import eod_review_prompt
        result = eod_review_prompt(
            outcomes=["AAPL BUY"],
            quality_summary="Test summary line",
        )
        assert "Decision Quality Metrics" in result
        assert "Test summary line" in result


# ── Execution log ──


class TestExecutionLog:
    def test_log_roundtrip(self, tmp_path):
        import json
        from src.agent.quality.models import ExecutionRecord

        log_file = tmp_path / "execution_log.jsonl"
        entry = {
            "decision_index": 0,
            "symbol": "AAPL",
            "action": "BUY",
            "order_id": "test-123",
            "filled_qty": 10.0,
            "filled_price": 150.0,
            "ts": "2026-01-05T10:00:00",
        }
        log_file.write_text(json.dumps(entry) + "\n")
        parsed = ExecutionRecord.model_validate_json(log_file.read_text().strip())
        assert parsed.order_id == "test-123"
        assert parsed.filled_qty == 10.0

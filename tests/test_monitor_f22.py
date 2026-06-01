"""F22: monitor.json structured output + current_turn."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def workspace(tmp_path: Path):
    turns = tmp_path / "turns.jsonl"
    decisions = tmp_path / "decisions.jsonl"
    # F25: turns are keyed by ET trading date (et_date). Use tz-aware ET timestamps
    # so the session grouping is deterministic regardless of the test machine's tz.
    et_date = "2026-06-01"
    started_ts = "2026-06-01T09:30:00-04:00"
    end_ts = "2026-06-01T09:31:00-04:00"
    mid_ts = "2026-06-01T09:30:30-04:00"
    started_ts2 = "2026-06-01T10:00:00-04:00"
    end_ts2 = "2026-06-01T10:01:00-04:00"

    turns.write_text(
        json.dumps({
            "turn_id": "R1", "started_at": started_ts, "ts": end_ts,
            "date": et_date, "et_date": et_date, "turn_type": "research",
            "model": "test", "num_decisions": 2, "cost_usd": 1.5,
            "duration_ms": 30000, "summary": "Research: BUY AAPL(0.8), HOLD MSFT(0.5)",
            "health": "ok",
        }) + "\n"
        + json.dumps({
            "turn_id": "I1", "started_at": started_ts2, "ts": end_ts2,
            "date": et_date, "et_date": et_date, "turn_type": "intraday",
            "model": "test", "num_decisions": 0, "cost_usd": 0.3,
            "duration_ms": 5000, "summary": "Intraday: no decisions",
            "health": "ok",
        }) + "\n"
    )

    decisions.write_text(
        json.dumps({
            "ts": mid_ts, "symbol": "AAPL", "action": "BUY",
            "confidence": 0.8, "reason": "Strong momentum and breakout",
            "source": "agent", "turn_id": "R1",
        }) + "\n"
        + json.dumps({
            "ts": mid_ts, "symbol": "MSFT", "action": "HOLD",
            "confidence": 0.5, "reason": "Neutral outlook",
            "source": "agent",
        }) + "\n"
    )

    return tmp_path, turns, decisions


class TestTurnsSummary:
    def test_structured_recent(self, workspace):
        _, turns_path, _ = workspace
        from src.agent.steering.runtime import _turns_summary
        result = _turns_summary(turns_path, session="2026-06-01")

        assert result["today_count"] == 2
        assert result["today_cost_usd"] == 1.8
        assert len(result["recent"]) == 2

        r1 = result["recent"][0]
        assert r1["id"] == "R1"
        assert r1["type"] == "research"
        assert r1["num_decisions"] == 2
        assert r1["summary"].startswith("Research:")
        assert r1["health"] == "ok"
        assert isinstance(r1["cost_usd"], float)

    def test_empty_file(self, tmp_path):
        from src.agent.steering.runtime import _turns_summary
        result = _turns_summary(tmp_path / "nonexistent.jsonl")
        assert result["today_count"] == 0
        assert result["recent"] == []


class TestDecisionsTail:
    def test_structured_decisions(self, workspace):
        _, turns_path, decisions_path = workspace
        from src.agent.steering.runtime import _decisions_tail
        result = _decisions_tail(decisions_path, turns_path)

        assert len(result) == 2
        d0 = result[0]
        assert d0["symbol"] == "AAPL"
        assert d0["action"] == "BUY"
        assert d0["confidence"] == 0.8
        assert d0["source"] == "agent"
        assert d0["turn_id"] == "R1"

    def test_correlates_turn_id_by_started_at(self, workspace):
        _, turns_path, decisions_path = workspace
        from src.agent.steering.runtime import _decisions_tail
        result = _decisions_tail(decisions_path, turns_path)
        d1 = result[1]
        assert d1["symbol"] == "MSFT"
        assert d1["turn_id"] == "R1"

    def test_reason_not_truncated(self, tmp_path):
        """F22: reasons are no longer truncated — the TUI overlay constrains display."""
        from src.agent.steering.runtime import _decisions_tail
        decisions_path = tmp_path / "decisions.jsonl"
        long_reason = "A" * 100
        decisions_path.write_text(json.dumps({
            "ts": datetime.now().isoformat(), "symbol": "AAPL", "action": "BUY",
            "reason": long_reason, "source": "agent",
        }) + "\n")
        result = _decisions_tail(decisions_path)
        assert len(result[0]["reason"]) == 100

    def test_empty_file(self, tmp_path):
        from src.agent.steering.runtime import _decisions_tail
        result = _decisions_tail(tmp_path / "nonexistent.jsonl")
        assert result == []


class TestCurrentTurn:
    def test_set_and_clear(self):
        from src.agent.steering.runtime import SteeringRuntime
        executor = MagicMock()
        executor.journal.root = Path("/tmp/test")
        orchestrator = MagicMock()
        rt = SteeringRuntime.__new__(SteeringRuntime)
        rt._current_turn = None

        rt.set_current_turn("I3", "intraday")
        assert rt._current_turn is not None
        assert rt._current_turn["id"] == "I3"
        assert rt._current_turn["type"] == "intraday"
        assert "started_at" in rt._current_turn

        rt.clear_current_turn()
        assert rt._current_turn is None

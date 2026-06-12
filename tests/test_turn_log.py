"""F22: turn_id generation, summary builder, and record_turn extensions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.logs.turn import build_turn_summary, generate_turn_id, record_turn


@pytest.fixture
def turns_file(tmp_path: Path) -> Path:
    return tmp_path / "turns.jsonl"


class TestGenerateTurnId:
    def test_first_turn_of_type(self, turns_file):
        assert generate_turn_id(turns_file, "research") == "R1"

    def test_sequential_same_type(self, turns_file):
        from datetime import datetime
        today = datetime.now().date().isoformat()
        for i in range(1, 4):
            rec = {"turn_id": f"I{i}", "date": today, "turn_type": "intraday"}
            turns_file.parent.mkdir(parents=True, exist_ok=True)
            with turns_file.open("a") as f:
                f.write(json.dumps(rec) + "\n")
        assert generate_turn_id(turns_file, "intraday") == "I4"

    def test_independent_type_counters(self, turns_file):
        from datetime import datetime
        today = datetime.now().date().isoformat()
        for tid, tt in [("R1", "research"), ("I1", "intraday"), ("I2", "intraday")]:
            rec = {"turn_id": tid, "date": today, "turn_type": tt}
            turns_file.parent.mkdir(parents=True, exist_ok=True)
            with turns_file.open("a") as f:
                f.write(json.dumps(rec) + "\n")
        assert generate_turn_id(turns_file, "research") == "R2"
        assert generate_turn_id(turns_file, "intraday") == "I3"
        assert generate_turn_id(turns_file, "wake") == "W1"

    def test_ignores_other_dates(self, turns_file):
        # F25: sessions are keyed by et_date, so a prior session's turn doesn't
        # bump today's sequence.
        rec = {"turn_id": "R5", "et_date": "2020-01-01", "turn_type": "research"}
        turns_file.parent.mkdir(parents=True, exist_ok=True)
        with turns_file.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        assert generate_turn_id(turns_file, "research") == "R1"

    def test_all_type_prefixes(self, turns_file):
        assert generate_turn_id(turns_file, "research") == "R1"
        assert generate_turn_id(turns_file, "intraday") == "I1"
        assert generate_turn_id(turns_file, "wake") == "W1"
        assert generate_turn_id(turns_file, "eod") == "E1"
        assert generate_turn_id(turns_file, "reconcile") == "C1"

    def test_unknown_type_uses_T(self, turns_file):
        assert generate_turn_id(turns_file, "custom") == "T1"


class TestBuildTurnSummary:
    def test_no_decisions(self):
        assert build_turn_summary("research", []) == "Research: no decisions"

    def test_with_decisions(self):
        decisions = [
            {"symbol": "AAPL", "action": "BUY", "confidence": 0.8},
            {"symbol": "MSFT", "action": "HOLD", "confidence": 0.5},
        ]
        result = build_turn_summary("intraday", decisions)
        assert result == "Intraday: BUY AAPL(0.8), HOLD MSFT(0.5)"

    def test_more_than_four_truncated(self):
        decisions = [
            {"symbol": f"SYM{i}", "action": "BUY", "confidence": 0.5}
            for i in range(6)
        ]
        result = build_turn_summary("research", decisions)
        assert "+2 more" in result
        assert "SYM0" in result
        assert "SYM3" in result
        assert "SYM4" not in result

    def test_no_confidence(self):
        decisions = [{"symbol": "AAPL", "action": "BUY", "confidence": None}]
        result = build_turn_summary("wake", decisions)
        assert result == "Wake: BUY AAPL"

    def test_eod_label(self):
        assert build_turn_summary("eod", []) == "EOD review: no decisions"

    def test_reconcile_label(self):
        assert build_turn_summary("reconcile", []) == "Reconcile: no decisions"


class TestRecordTurnExtended:
    def test_includes_turn_id_and_summary(self, turns_file):
        rec = record_turn(
            turns_file, turn_type="research", model="test", num_decisions=0,
            raw=None, turn_id="R1", summary="Research: no decisions",
        )
        assert rec["turn_id"] == "R1"
        assert rec["summary"] == "Research: no decisions"
        assert rec["health"] == "ok"

    def test_error_health(self, turns_file):
        rec = record_turn(
            turns_file, turn_type="intraday", model="test", num_decisions=0,
            raw=None, turn_id="I1", error=True,
        )
        assert rec["health"] == "error"

    def test_persisted_to_file(self, turns_file):
        record_turn(
            turns_file, turn_type="wake", model="test", num_decisions=2,
            raw=None, turn_id="W1", summary="Wake: BUY AAPL(0.8), SELL MSFT(0.6)",
        )
        lines = turns_file.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["turn_id"] == "W1"
        assert data["summary"].startswith("Wake:")

    def test_backward_compat_no_turn_id(self, turns_file):
        rec = record_turn(
            turns_file, turn_type="research", model="test", num_decisions=0, raw=None,
        )
        assert rec["turn_id"] == ""
        assert rec["health"] == "ok"

"""Unit tests for surge-related agent tools (market.surge_list, surge_analyze)."""

from datetime import date, datetime
from pathlib import Path

import pytest

from src.agent.tools.market import surge_analyze, surge_list
from src.surge.records import SurgeAnalysis, SurgeCause, SurgeRecord
from src.surge.store import SurgeStore


@pytest.fixture
def store(tmp_path: Path, monkeypatch):
    """Create a SurgeStore in a temp dir and patch AGENT_JOURNAL_ROOT."""
    s = SurgeStore(base_dir=tmp_path / "surge")
    monkeypatch.setenv("AGENT_JOURNAL_ROOT", str(tmp_path))
    # Seed a record so surge_analyze validation passes.
    s.write_records([
        SurgeRecord(
            symbol="AAPL",
            trading_date=date.today(),
            direction="up",
            close_prev=150.0,
            close_today=162.75,
            change_pct=8.5,
            volume=10_000_000,
            avg_volume_20d=5_000_000,
            volume_ratio=2.0,
            high_today=165.0,
            low_today=160.0,
            detected_at=datetime.now(),
        )
    ])
    return s


class TestSurgeList:
    def test_returns_records(self, store):
        result = surge_list()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["symbol"] == "AAPL"

    def test_empty_when_no_records(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("AGENT_JOURNAL_ROOT", str(tmp_path))
        result = surge_list()
        assert result == []


class TestSurgeAnalyze:
    def test_ok(self, store):
        result = surge_analyze(
            "AAPL",
            date.today().isoformat(),
            "news",
            "pre-market +3%, unusual volume",
            "no pre-market scanner",
        )
        assert result["status"] == "ok"

    def test_invalid_cause(self, store):
        result = surge_analyze(
            "AAPL", date.today().isoformat(), "invalid_cause", "", ""
        )
        assert result["status"] == "error"
        assert "Invalid cause" in result["message"]

    def test_unknown_symbol_rejected(self, store):
        result = surge_analyze(
            "MSFT", date.today().isoformat(), "news", "", ""
        )
        assert result["status"] == "error"
        assert "No SurgeRecord found" in result["message"]

    def test_analysis_appended(self, store):
        surge_analyze("AAPL", date.today().isoformat(), "sector", "sector rotation", "no sector flow data")
        analyses = store.read_analyses()
        assert len(analyses) == 1
        assert analyses[0].estimated_cause == SurgeCause.SECTOR
        assert analyses[0].leading_indicators == "sector rotation"

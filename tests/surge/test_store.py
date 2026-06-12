"""Unit tests for src.surge.store — SurgeStore JSONL read/write."""

import json
import tempfile
from datetime import date, datetime
from pathlib import Path

import pytest

from src.surge.records import SurgeAnalysis, SurgeCause, SurgeRecord
from src.surge.store import SurgeStore, _atomic_append
# Torn-line / valid-json / empty-file reading moved to src.core.jsonl (R4); those
# low-level cases are now covered by tests/test_jsonl.py. _atomic_append remains here.


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _record(symbol: str = "AAPL", d: date | None = None, change_pct: float = 8.5) -> SurgeRecord:
    return SurgeRecord(
        symbol=symbol,
        trading_date=d or date.today(),
        direction="up" if change_pct > 0 else "down",
        close_prev=150.0,
        close_today=162.75,
        change_pct=change_pct,
        volume=10_000_000,
        avg_volume_20d=5_000_000,
        volume_ratio=2.0,
        high_today=165.0,
        low_today=160.0,
        detected_at=datetime.now(),
    )


def _analysis(symbol: str = "AAPL", d: date | None = None) -> SurgeAnalysis:
    return SurgeAnalysis(
        symbol=symbol,
        trading_date=d or date.today(),
        estimated_cause=SurgeCause.NEWS,
        leading_indicators="pre-market +3%",
        information_gap="no pre-market scanner",
        analyzed_at=datetime.now(),
    )


# ---------------------------------------------------------------------------
# low-level helpers
# ---------------------------------------------------------------------------

class TestLowLevel:
    def test_atomic_append(self, tmp_path: Path):
        f = tmp_path / "test.jsonl"
        _atomic_append(f, ['{"a":1}'])
        assert f.exists()
        data = json.loads(f.read_text().strip())
        assert data == {"a": 1}

    def test_atomic_append_preserves_existing(self, tmp_path: Path):
        f = tmp_path / "test.jsonl"
        f.write_text('{"a":1}\n')
        _atomic_append(f, ['{"b":2}'])
        lines = f.read_text().strip().split("\n")
        assert len(lines) == 2


# ---------------------------------------------------------------------------
# SurgeStore
# ---------------------------------------------------------------------------

class TestSurgeStore:
    def test_write_and_read(self, tmp_path: Path):
        store = SurgeStore(base_dir=tmp_path)
        r = _record()
        n = store.write_records([r])
        assert n == 1
        records = store.read_records()
        assert len(records) == 1
        assert records[0].symbol == "AAPL"

    def test_idempotent_write(self, tmp_path: Path):
        store = SurgeStore(base_dir=tmp_path)
        r = _record()
        assert store.write_records([r]) == 1
        assert store.write_records([r]) == 0  # duplicate skipped

    def test_write_multiple(self, tmp_path: Path):
        store = SurgeStore(base_dir=tmp_path)
        records = [
            _record("AAPL", change_pct=8.5),
            _record("MSFT", change_pct=9.0),
            _record("GOOGL", change_pct=-7.2),
        ]
        n = store.write_records(records)
        assert n == 3
        all_records = store.read_records()
        assert len(all_records) == 3

    def test_read_filtered_by_date(self, tmp_path: Path):
        store = SurgeStore(base_dir=tmp_path)
        d1 = date(2026, 6, 1)
        d2 = date(2026, 6, 2)
        store.write_records([_record("AAPL", d=d1), _record("MSFT", d=d2)])
        assert len(store.read_records(d=d1)) == 1
        assert len(store.read_records(d=d2)) == 1
        assert len(store.read_records(d=date(2026, 6, 3))) == 0

    # -- analyses ----------------------------------------------------------

    def test_append_analysis(self, tmp_path: Path):
        store = SurgeStore(base_dir=tmp_path)
        store.write_records([_record("AAPL")])
        store.append_analysis(_analysis("AAPL"))
        analyses = store.read_analyses()
        assert len(analyses) == 1
        assert analyses[0].estimated_cause == SurgeCause.NEWS

    def test_append_analysis_rejects_unknown_symbol(self, tmp_path: Path):
        store = SurgeStore(base_dir=tmp_path)
        with pytest.raises(ValueError, match="No SurgeRecord found"):
            store.append_analysis(_analysis("MSFT"))

    def test_analysis_read_filtered_by_date(self, tmp_path: Path):
        store = SurgeStore(base_dir=tmp_path)
        d1 = date(2026, 6, 1)
        d2 = date(2026, 6, 2)
        store.write_records([_record("AAPL", d=d1), _record("MSFT", d=d2)])
        store.append_analysis(_analysis("AAPL", d=d1))
        store.append_analysis(_analysis("MSFT", d=d2))
        assert len(store.read_analyses(d=d1)) == 1
        assert len(store.read_analyses()) == 2

    def test_empty_store(self, tmp_path: Path):
        store = SurgeStore(base_dir=tmp_path)
        assert store.read_records() == []
        assert store.read_analyses() == []

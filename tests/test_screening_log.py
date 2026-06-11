"""Screening capture (F72): scan snapshot persistence + verdict journal reads.

Covers the funnel-logging contract: the scoreboard snapshot is saved atomically
under its ET trading date and survives a JSON round-trip unchanged (PBT); a
save failure never raises (fail-honest — it must not sink the scan the agent is
waiting on); verdict reads are lenient about torn/corrupt lines.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from hypothesis import given
from hypothesis import strategies as st

from src.agent import prompts, screening_log
from src.agent.turn_log import compute_et_date

TS = datetime(2026, 6, 11, 9, 31, tzinfo=timezone.utc)


def _rows() -> list[dict]:
    return [
        {"symbol": "AAPL", "close": 234.5, "chg_1d": 0.3, "chg_5d": 1.2,
         "chg_20d": 4.0, "rsi_14": 61.2, "macd_hist": 0.45, "vol_ratio": 1.1,
         "dist_high_20d_pct": -2.3},
        {"symbol": "XYZ", "error": "no data"},
    ]


class TestRecordScan:
    def test_writes_snapshot_keyed_by_et_date(self, tmp_path):
        path = screening_log.record_scan(_rows(), root=tmp_path, ts=TS)
        et_date = compute_et_date(TS)
        assert path == tmp_path / "screening" / f"{et_date}.scan.json"
        doc = json.loads(path.read_text())
        assert doc["et_date"] == et_date
        assert doc["ts"] == TS.isoformat()
        assert doc["count"] == 2
        assert doc["rows"] == _rows()  # error rows included

    def test_same_day_rerun_overwrites_with_latest(self, tmp_path):
        screening_log.record_scan(_rows(), root=tmp_path, ts=TS)
        later = TS.replace(hour=15)
        rows2 = [{"symbol": "MSFT", "close": 500.0}]
        path = screening_log.record_scan(rows2, root=tmp_path, ts=later)
        doc = json.loads(path.read_text())
        assert doc["ts"] == later.isoformat()
        assert doc["rows"] == rows2

    def test_save_failure_returns_none_without_raising(self, tmp_path):
        # a *file* where the screening dir should be → mkdir fails
        (tmp_path / "screening").write_text("not a directory")
        assert screening_log.record_scan(_rows(), root=tmp_path, ts=TS) is None

    def test_env_root_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_JOURNAL_ROOT", str(tmp_path))
        path = screening_log.record_scan(_rows(), ts=TS)
        assert path is not None and path.is_relative_to(tmp_path)


# scoreboard-shaped rows: symbol + optional numeric/None fields or an error row
_row_st = st.one_of(
    st.fixed_dictionaries({
        "symbol": st.text(alphabet="ABCDEFGHIJ", min_size=1, max_size=5),
        "close": st.one_of(st.none(), st.floats(allow_nan=False, allow_infinity=False)),
        "rsi_14": st.one_of(st.none(), st.floats(allow_nan=False, allow_infinity=False)),
    }),
    st.fixed_dictionaries({
        "symbol": st.text(alphabet="ABCDEFGHIJ", min_size=1, max_size=5),
        "error": st.text(max_size=40),
    }),
)


class TestScanRoundTrip:
    @given(rows=st.lists(_row_st, max_size=8))
    def test_record_then_read_preserves_rows(self, rows, tmp_path_factory):
        root = tmp_path_factory.mktemp("ws")
        screening_log.record_scan(rows, root=root, ts=TS)
        doc = screening_log.read_scan(root, compute_et_date(TS))
        assert doc is not None and doc["rows"] == rows

    def test_read_missing_or_corrupt_is_none(self, tmp_path):
        assert screening_log.read_scan(tmp_path, "2026-06-11") is None
        p = screening_log.scan_path(tmp_path, "2026-06-11")
        p.parent.mkdir(parents=True)
        p.write_text("{torn")
        assert screening_log.read_scan(tmp_path, "2026-06-11") is None


class TestReadVerdicts:
    def test_lenient_parse_skips_corrupt_lines(self, tmp_path):
        p = screening_log.verdicts_path(tmp_path, "2026-06-11")
        p.parent.mkdir(parents=True)
        p.write_text(
            '{"ts": "t1", "symbol": "NVDA", "verdict": "passed", "reason": "RSI 82"}\n'
            "{torn line\n"
            "\n"
            '"not a dict"\n'
            '{"ts": "t2", "symbol": "TMO", "verdict": "custom-word", "reason": "x"}\n'
        )
        recs = screening_log.read_verdicts(tmp_path, "2026-06-11")
        assert [r["symbol"] for r in recs] == ["NVDA", "TMO"]
        # unknown verdict values are kept as-is (journal is evidence, not schema)
        assert recs[1]["verdict"] == "custom-word"

    def test_missing_file_is_empty(self, tmp_path):
        assert screening_log.read_verdicts(tmp_path, "2026-06-11") == []


class TestPromptMandate:
    def test_morning_research_includes_screening_journal(self):
        p = prompts.morning_research_prompt(["AAPL", "MSFT"], held=["NVDA"])
        assert "Screening journal" in p
        assert ".verdicts.jsonl" in p
        assert "entered|watchlist|passed" in p

    def test_multi_agent_round1_includes_screening_journal(self):
        p = prompts.multi_research_initial_prompt(["AAPL"], held=["NVDA"])
        assert "Screening journal" in p
        assert ".verdicts.jsonl" in p
        # round 1 forbids decisions.jsonl — the journal must be carved out
        assert "separate from decisions.jsonl" in p

    def test_intraday_prompt_unchanged(self):
        assert "Screening journal" not in prompts.intraday_prompt(held=["NVDA"])

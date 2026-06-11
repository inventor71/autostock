"""F25 Unit A (daemon-timeline): ET-date sessions, market rule, interventions."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from hypothesis import given, strategies as st

from src.agent.logs.turn import compute_et_date
from src.agent.steering.runtime import (
    _DEFAULT_MARKET_RULE,
    _interventions_tail,
    _iso,
    _resolve_session_et_date,
    _turns_summary,
)


class TestComputeEtDate:
    def test_et_morning_is_same_date(self):
        # 10:00 ET on 2026-06-01 → ET date 2026-06-01
        ts = "2026-06-01T10:00:00-04:00"
        assert compute_et_date(ts) == "2026-06-01"

    def test_kst_morning_maps_to_previous_et_date(self):
        # 09:30 KST 2026-06-01 (= 20:30 EDT 2026-05-31) → ET date 2026-05-31
        ts = "2026-06-01T09:30:00+09:00"
        assert compute_et_date(ts) == "2026-05-31"

    def test_after_hours_does_not_cross_et_midnight(self):
        # 20:00 ET (after-hours close) stays on the same ET date
        ts = "2026-06-01T19:59:00-04:00"
        assert compute_et_date(ts) == "2026-06-01"

    def test_bad_string_falls_back_to_today_et(self):
        today_et = datetime.now(timezone.utc).astimezone().isoformat()
        # garbage → current ET date (never raises)
        out = compute_et_date("not-a-date")
        assert len(out) == 10 and out.count("-") == 2

    @given(st.integers(min_value=0, max_value=2_000_000_000))
    def test_never_raises_and_returns_iso_date(self, epoch: int):
        dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
        out = compute_et_date(dt.isoformat())
        # YYYY-MM-DD
        assert len(out) == 10 and out[4] == "-" and out[7] == "-"


class TestIso:
    def test_naive_gets_localized(self):
        out = _iso("2026-06-01T09:30:00")
        assert out.startswith("2026-06-01T09:30:00")
        # a tz offset is appended
        assert ("+" in out[-6:]) or ("-" in out[-6:])

    def test_aware_preserved(self):
        assert _iso("2026-06-01T09:30:00-04:00") == "2026-06-01T09:30:00-04:00"

    def test_empty(self):
        assert _iso("") == "" and _iso(None) == ""


class TestSessionEtDate:
    def test_returns_weekday(self):
        d = _resolve_session_et_date()
        wd = datetime.fromisoformat(d).weekday()
        assert wd < 5  # never a Sat/Sun

    def test_custom_rule_accepted(self):
        d = _resolve_session_et_date({"pre_open": "04:00", "after_close": "20:00"})
        assert len(d) == 10


class TestMarketRule:
    def test_default_shape(self):
        for k in ("tz", "pre_open", "regular_open", "regular_close", "after_close"):
            assert k in _DEFAULT_MARKET_RULE
        assert _DEFAULT_MARKET_RULE["tz"] == "America/New_York"


class TestInterventionsTail:
    def _write(self, path: Path, recs: list[dict]) -> None:
        path.write_text("\n".join(json.dumps(r) for r in recs) + "\n")

    def test_only_trade_verbs(self, tmp_path):
        p = tmp_path / "human_directives.jsonl"
        self._write(p, [
            {"ts": "2026-06-01T10:00:00-04:00", "command": "buy",
             "args": {"symbol": "aapl"}, "outcome": "executed", "detail": "10sh"},
            {"ts": "2026-06-01T10:01:00-04:00", "command": "pause",
             "args": {}, "outcome": "applied", "detail": ""},
            {"ts": "2026-06-01T10:02:00-04:00", "command": "note",
             "args": {}, "outcome": "applied", "detail": "watch META"},
            {"ts": "2026-06-01T10:03:00-04:00", "command": "flatten",
             "args": {"symbol": "TSLA"}, "outcome": "executed", "detail": "closed"},
        ])
        out = _interventions_tail(p)
        verbs = [o["verb"] for o in out]
        assert verbs == ["buy", "flatten"]  # pause/note excluded
        assert out[0]["symbol"] == "AAPL"   # uppercased
        assert out[0]["et_date"] == "2026-06-01"
        assert out[1]["symbol"] == "TSLA"

    def test_missing_file(self, tmp_path):
        assert _interventions_tail(tmp_path / "nope.jsonl") == []

    def test_secrets_masked_in_detail(self, tmp_path):
        # SECURITY-03: outcome/detail are free-form; secrets must be masked.
        p = tmp_path / "human_directives.jsonl"
        self._write(p, [
            {"ts": "2026-06-01T10:00:00-04:00", "command": "buy",
             "args": {"symbol": "AAPL"}, "outcome": "executed",
             "detail": "token=abcdef0123456789abcdef0123 placed"},
        ])
        out = _interventions_tail(p)
        assert "abcdef0123456789abcdef0123" not in out[0]["detail"]

    def test_torn_line_skipped(self, tmp_path):
        p = tmp_path / "human_directives.jsonl"
        p.write_text(
            json.dumps({"ts": "2026-06-01T10:00:00-04:00", "command": "buy",
                        "args": {"symbol": "AAPL"}, "outcome": "executed"}) + "\n"
            + '{"command": "sell", broken json\n'
        )
        out = _interventions_tail(p)
        assert len(out) == 1 and out[0]["verb"] == "buy"

    def test_et_date_filter_finds_trades_beyond_150_line_window(self, tmp_path):
        """F32: when many non-trade lines push trade entries beyond the old 150-line
        window, the ET-date filter still finds them."""
        p = tmp_path / "human_directives.jsonl"
        lines = []
        # 200 non-trade lines (pause/note) that would push a trade out of the
        # old 150-line window
        for i in range(200):
            lines.append({"ts": "2026-06-01T09:00:00-04:00", "command": "note",
                          "args": {}, "outcome": "applied"})
        # Then a buy trade at the end
        lines.append({"ts": "2026-06-01T10:00:00-04:00", "command": "buy",
                      "args": {"symbol": "AAPL"}, "outcome": "executed"})
        self._write(p, lines)
        # Without et_date (legacy): trade is found because it's in the last 150 lines
        out_legacy = _interventions_tail(p)
        assert len(out_legacy) == 1
        assert out_legacy[0]["verb"] == "buy"
        # With et_date filter: also found (and it scans the whole file)
        out_filtered = _interventions_tail(p, et_date="2026-06-01")
        assert len(out_filtered) == 1
        assert out_filtered[0]["verb"] == "buy"
        assert out_filtered[0]["symbol"] == "AAPL"

    def test_et_date_filter_excludes_other_dates(self, tmp_path):
        """F32: ET-date filter only returns entries matching the target date."""
        p = tmp_path / "human_directives.jsonl"
        self._write(p, [
            {"ts": "2026-05-30T10:00:00-04:00", "command": "buy",
             "args": {"symbol": "OLD"}, "outcome": "executed"},
            {"ts": "2026-06-01T10:00:00-04:00", "command": "buy",
             "args": {"symbol": "TODAY"}, "outcome": "executed"},
            {"ts": "2026-06-01T10:01:00-04:00", "command": "sell",
             "args": {"symbol": "TODAY2"}, "outcome": "executed"},
        ])
        out = _interventions_tail(p, et_date="2026-06-01")
        verbs = [o["verb"] for o in out]
        assert verbs == ["buy", "sell"]
        assert out[0]["symbol"] == "TODAY"
        assert out[1]["symbol"] == "TODAY2"

    def test_et_date_filter_stops_at_date_boundary(self, tmp_path):
        """F32: scanning backwards stops collecting at the first entry from a
        different date (optimization; files are roughly chronological)."""
        p = tmp_path / "human_directives.jsonl"
        self._write(p, [
            {"ts": "2026-05-30T10:00:00-04:00", "command": "buy",
             "args": {"symbol": "OLD"}, "outcome": "executed"},
            {"ts": "2026-05-30T10:01:00-04:00", "command": "buy",
             "args": {"symbol": "OLD2"}, "outcome": "executed"},
            {"ts": "2026-06-01T10:00:00-04:00", "command": "buy",
             "args": {"symbol": "TODAY"}, "outcome": "executed"},
            {"ts": "2026-06-01T10:01:00-04:00", "command": "sell",
             "args": {"symbol": "TODAY2"}, "outcome": "executed"},
        ])
        out = _interventions_tail(p, et_date="2026-06-01")
        # Only today's entries; OLD/Old2 from 05-30 are excluded
        assert len(out) == 2
        assert all(o["et_date"] == "2026-06-01" for o in out)


class TestTurnsSummarySession:
    def test_filters_by_et_session(self, tmp_path):
        p = tmp_path / "turns.jsonl"
        p.write_text(
            json.dumps({"turn_id": "R1", "ts": "2026-06-01T10:00:00-04:00",
                        "et_date": "2026-06-01", "turn_type": "research",
                        "cost_usd": 1.0, "num_decisions": 1, "summary": "x",
                        "health": "ok"}) + "\n"
            + json.dumps({"turn_id": "R1", "ts": "2026-05-30T10:00:00-04:00",
                          "et_date": "2026-05-30", "turn_type": "research",
                          "cost_usd": 9.0, "num_decisions": 1, "summary": "old",
                          "health": "ok"}) + "\n"
        )
        out = _turns_summary(p, session="2026-06-01")
        assert out["today_count"] == 1
        assert out["today_cost_usd"] == 1.0
        assert out["recent"][0]["et_date"] == "2026-06-01"
        # ts forwarded as full ISO (not HH:MM)
        assert out["recent"][0]["ts"] == "2026-06-01T10:00:00-04:00"

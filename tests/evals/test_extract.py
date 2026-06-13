"""Scenario skeleton extractor: auto-fills only what the records contain,
marks the rest TODO_MANUAL. Token-zero, network-zero (bar fetcher injected)."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from src.evals.extract import TODO, extract_skeleton


def _workspace(tmp_path):
    ws = tmp_path / "ws"
    (ws / "positions").mkdir(parents=True)
    (ws / "positions" / "AAPL.md").write_text("# AAPL\nstop 300\n", encoding="utf-8")
    (ws / "lessons.md").write_text("## 17 — preempt armed exits\n", encoding="utf-8")
    (ws / "equity.jsonl").write_text("\n".join([
        json.dumps({"date": "2026-06-05", "equity": 100100.0, "cash": 90000.0,
                    "invested": 10100.0,
                    "positions": [{"symbol": "AAPL", "qty": 10.0, "avg": 309.0,
                                   "price": 311.0, "pnl": 20.0}]}),
        json.dumps({"date": "2026-06-09", "equity": 99000.0, "cash": 99000.0,
                    "invested": 0.0, "positions": []}),
    ]) + "\n", encoding="utf-8")
    (ws / "decisions.jsonl").write_text("\n".join([
        json.dumps({"ts": "2026-06-03T14:00:00", "symbol": "AAPL", "action": "ADJUST_STOP",
                    "stop": 300.0, "reason": "trail"}),
        json.dumps({"ts": "2026-06-09T14:00:00", "symbol": "AAPL", "action": "SELL",
                    "reason": "after the frozen date — must be excluded"}),
        json.dumps({"ts": "2026-06-04T14:00:00", "symbol": "MSFT", "action": "HOLD",
                    "reason": "other symbol — excluded"}),
    ]) + "\n", encoding="utf-8")
    return ws


def _bars():
    idx = pd.date_range("2026-01-02", periods=120, freq="B")
    base = pd.Series(range(120), index=idx) * 0.5 + 250.0
    return pd.DataFrame({"open": base, "high": base + 2, "low": base - 2,
                         "close": base + 1, "volume": 20_000_000}, index=idx)


def test_skeleton_fills_records_and_marks_the_rest(tmp_path):
    ws = _workspace(tmp_path)
    s = extract_skeleton(workspace=ws, symbol="AAPL", asof=date(2026, 6, 8),
                         turn_type="intraday", bar_fetcher=lambda sym, d: _bars())

    # auto-filled from records / pinned bars through the REAL tool functions
    assert s.held == {"AAPL": {"qty": 10.0, "avg_entry_price": 309.0, "side": "long"}}
    assert s.tool_fixtures["account"]["_"]["equity"] == 100100.0  # snapshot <= date
    assert s.tool_fixtures["quote"]["AAPL"]["price"] == _bars()["close"].iloc[-1]
    assert "rsi_14" in s.tool_fixtures["indicators"]["AAPL"]
    assert s.prices["AAPL"] == _bars()["close"].iloc[-1]

    # history is symbol-filtered and date-bounded (no future leakage)
    assert [d["ts"][:10] for d in s.decisions_history] == ["2026-06-03"]

    # the non-reconstructable slice is explicitly marked, never silently empty
    dumped = json.dumps(s.model_dump(mode="json"))
    assert TODO in s.tool_fixtures["news"]["AAPL"]["news"][0]["title"]
    assert TODO in s.workspace_files["positions/AAPL.md"]
    assert dumped.count(TODO) >= 4


def test_skeleton_without_records_still_validates(tmp_path):
    ws = tmp_path / "empty"
    ws.mkdir()
    s = extract_skeleton(workspace=ws, symbol="NVDA", asof=date(2026, 6, 8),
                         turn_type="wake", bar_fetcher=lambda sym, d: pd.DataFrame())
    assert s.universe == ["NVDA"]
    assert s.held == {} and "quote" not in s.tool_fixtures

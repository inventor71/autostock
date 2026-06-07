from datetime import datetime, timedelta

from src.benchmark.models import EquitySnapshot
from src.benchmark.store import EquityRecorder
from src.core.models import PortfolioState, Position


def _pf(equity: float, cash: float = 0.0, positions=None) -> PortfolioState:
    return PortfolioState(cash=cash, equity=equity, positions=positions or {})


def test_record_then_load_roundtrip(tmp_path):
    rec = EquityRecorder(tmp_path)
    pos = Position(symbol="AAPL", qty=1, avg_entry_price=100.0)
    snap = rec.record("rsi", _pf(1000.0, cash=500.0, positions={"AAPL": pos}), "acct123…")
    assert isinstance(snap, EquitySnapshot)

    loaded = rec.load("rsi")
    assert len(loaded) == 1
    assert loaded[0].equity == 1000.0
    assert loaded[0].cash == 500.0
    assert loaded[0].position_count == 1
    assert loaded[0].account_masked == "acct123…"


def test_record_never_persists_raw_secret(tmp_path):
    rec = EquityRecorder(tmp_path)
    rec.record("rsi", _pf(1000.0), account_masked="abcd1234…")
    text = (tmp_path / "equity" / "rsi.jsonl").read_text()
    # only the masked id is present; no field named secret/api_key
    assert "abcd1234…" in text
    assert "secret" not in text.lower()
    assert "api_key" not in text.lower()


def test_non_finite_equity_skipped(tmp_path):
    rec = EquityRecorder(tmp_path)
    assert rec.record("rsi", _pf(float("nan")), "x") is None
    assert rec.load("rsi") == []


def test_compact_drops_old(tmp_path):
    rec = EquityRecorder(tmp_path)
    now = datetime(2026, 6, 1)
    old = now - timedelta(days=400)
    rec.record("rsi", _pf(900.0), "x", ts=old)
    rec.record("rsi", _pf(1000.0), "x", ts=now)
    kept = rec.compact("rsi", retention_days=365, now=now)
    assert kept == 1
    series = rec.load("rsi")
    assert len(series) == 1
    assert series[0].equity == 1000.0


def test_compact_noop_when_all_fresh(tmp_path):
    rec = EquityRecorder(tmp_path)
    now = datetime(2026, 6, 1)
    rec.record("rsi", _pf(1000.0), "x", ts=now)
    assert rec.compact("rsi", retention_days=365, now=now) == 1

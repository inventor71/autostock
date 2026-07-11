"""F95: quote warm-cache — QuoteBook + candidate selection (pure) and the
refresh_quotes → quotes.json producer (integration on the bus worker)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from src.agent.executor import DecisionExecutor
from src.agent.journal import Journal
from src.agent.steering.quotes import QuoteBook, quote_candidates
from src.agent.steering.runtime import SteeringRuntime
from src.execution.brokers.simulated_broker import SimulatedBroker
from src.risk.manager import RiskManager

T0 = datetime(2026, 7, 6, 17, 0, 0, tzinfo=timezone.utc)


# ---- pure: quote_candidates ------------------------------------------------ #

def test_candidates_priority_dedup_and_uppercase():
    # held first, then orders (MSFT deduped), cap truncates before recent.
    c = quote_candidates(["AAPL", "msft"], ["MSFT", "TSLA"], ["NVDA"], cap=3)
    assert c == ["AAPL", "MSFT", "TSLA"]


def test_candidates_include_recent_when_room():
    c = quote_candidates(["AAPL"], ["MSFT"], ["nvda", "AAPL"], cap=30)
    assert c == ["AAPL", "MSFT", "NVDA"]  # recent AAPL deduped


def test_candidates_skip_placeholder_and_empty():
    assert quote_candidates([], [], ["?", "", None]) == []


# ---- pure: QuoteBook ------------------------------------------------------- #

def test_quotebook_ttl_expiry():
    qb = QuoteBook(ttl_sec=10)
    qb.put("AAPL", 100.0, ts=T0)
    assert qb.get("AAPL", now=T0) == 100.0
    assert qb.get("AAPL", now=T0 + timedelta(seconds=9)) == 100.0
    assert qb.get("AAPL", now=T0 + timedelta(seconds=11)) is None


def test_quotebook_payload_prices_and_errors_fresh_only():
    qb = QuoteBook(ttl_sec=10)
    qb.put("AAPL", 100.0, ts=T0)
    qb.put_error("XYZ", "no_data", ts=T0)
    p = qb.as_payload(now=T0)
    assert p["quotes"]["AAPL"] == {"price": 100.0, "ts": T0.isoformat()}
    assert p["quotes"]["XYZ"] == {"error": "no_data", "ts": T0.isoformat()}
    assert p["ttl_seconds"] == 10
    # once stale, entries drop out entirely (TUI then shows "조회 중").
    assert qb.as_payload(now=T0 + timedelta(seconds=20))["quotes"] == {}


def test_quotebook_put_and_error_are_mutually_exclusive():
    qb = QuoteBook()
    qb.put_error("AAPL", "no_data", ts=T0)
    qb.put("AAPL", 50.0, ts=T0)
    assert qb.get("AAPL", now=T0) == 50.0
    assert qb.as_payload(now=T0)["quotes"]["AAPL"]["price"] == 50.0
    qb.put_error("AAPL", "no_data", ts=T0)  # a later failure supersedes the price
    assert qb.get("AAPL", now=T0) is None
    assert qb.as_payload(now=T0)["quotes"]["AAPL"] == {"error": "no_data", "ts": T0.isoformat()}


# ---- integration: refresh_quotes → quotes.json ----------------------------- #

class _Orch:
    last_new_decisions: list = []
    last_kept: list = []


class _Provider:
    """Returns a fixed price for AAPL, raises for the rest (fail-honest path)."""
    def get_latest_price(self, symbol):
        if symbol == "AAPL":
            return 100.0
        raise RuntimeError("no market data")

    def get_bars(self, symbol, timeframe=None, start=None, end=None, limit=100):
        idx = pd.date_range("2024-01-01", periods=1, freq="D")
        return pd.DataFrame({"open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]}, index=idx)


def _runtime(tmp_path):
    broker = SimulatedBroker(initial_capital=100_000.0)
    ex = DecisionExecutor(broker, RiskManager(use_bracket_orders=True), _Provider(),
                          journal=Journal(root=tmp_path / "ws"), universe=["AAPL", "MSFT"])
    return SteeringRuntime(ex, _Orch(), steering_dir=tmp_path / "steering", token="tok")


def _wait(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_refresh_quotes_publishes_prices_and_marks_failures(tmp_path):
    rt = _runtime(tmp_path)
    root = rt.executor.journal.root
    root.mkdir(parents=True, exist_ok=True)
    # two recently-decided symbols become candidates; AAPL prices, MSFT fails.
    with (root / "decisions.jsonl").open("w", encoding="utf-8") as fh:
        for sym in ("AAPL", "MSFT"):
            fh.write(json.dumps({"symbol": sym, "action": "BUY",
                                 "ts": datetime.now(timezone.utc).isoformat()}) + "\n")
    rt.bus.start()
    try:
        rt.refresh_quotes()
        assert _wait(lambda: rt.channel.quotes_file.exists())
        # give the single worker a beat to finish the write
        assert _wait(lambda: "AAPL" in json.loads(rt.channel.quotes_file.read_text()).get("quotes", {}))
        data = json.loads(rt.channel.quotes_file.read_text())
    finally:
        rt.bus.stop()

    assert data["quotes"]["AAPL"]["price"] == 100.0
    assert data["quotes"]["MSFT"] == {"error": "no_data", "ts": data["quotes"]["MSFT"]["ts"]}
    assert data["provider"] == "_Provider"
    assert "updated" in data and "published_at" in data


def test_refresh_quotes_no_candidates_publishes_empty(tmp_path):
    rt = _runtime(tmp_path)  # fresh broker: no positions/orders, no decisions file
    rt.bus.start()
    try:
        rt.refresh_quotes()
        assert _wait(lambda: rt.channel.quotes_file.exists())
        data = json.loads(rt.channel.quotes_file.read_text())
    finally:
        rt.bus.stop()
    assert data["quotes"] == {}

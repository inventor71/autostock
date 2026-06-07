"""F69: daemon lightweight system-health publish (steering/health.json).

The periodic publish must stay CHEAP — it runs only the no-external-call dimensions
and derives `account` from the snapshot the daemon already holds. These tests pin
that invariant (the regression the critic flagged: the full 9-dim check creates 5
brokers + pings the LLM every run) and the augmentation / stale-stamp behaviour.
"""

from __future__ import annotations

import json

from src.agent.executor import DecisionExecutor
from src.agent.journal import Journal
from src.agent.steering.runtime import SteeringRuntime
from src.execution.brokers.simulated import SimulatedBroker
from src.risk.manager import RiskManager


class _StubOrchestrator:
    def run_morning_research(self): ...
    def run_intraday(self, quotes=None): ...
    def run_eod_review(self, outcomes=None): ...
    def run_reconcile(self, context=""): return "ok"


class _Provider:
    def get_latest_price(self, symbol): return 100.0
    def get_bars(self, *a, **k): return None


def _runtime(tmp_path):
    broker = SimulatedBroker(initial_capital=100_000.0)
    ex = DecisionExecutor(broker, RiskManager(use_bracket_orders=True), _Provider(),
                          journal=Journal(root=tmp_path / "ws"), universe=["AAPL"])
    rt = SteeringRuntime(ex, _StubOrchestrator(), steering_dir=tmp_path / "steering",
                         token="tok")
    return rt


# Dimensions that hit the broker / LLM / network — these must NEVER appear in the
# periodic publish (they belong to scripts/health.py's full deep check only).
_EXPENSIVE = {"broker", "llm", "risk", "data_pipeline"}
# The cheap, local-only dimensions the daemon is allowed to run periodically.
_CHEAP = {"process", "logs", "config_env", "resources"}


def test_publish_health_writes_file_with_expected_shape(tmp_path):
    rt = _runtime(tmp_path)
    rt.publish_health()

    path = tmp_path / "steering" / "health.json"
    assert path.exists(), "publish_health must write steering/health.json"
    payload = json.loads(path.read_text())

    assert payload["overall"] in {"OK", "WARNING", "ERROR", "CRITICAL", "SKIPPED"}
    assert "summary" in payload
    # F69 stale-stamp so the TUI computes staleness from the real cadence.
    assert isinstance(payload["publish_interval_seconds"], int)


def test_periodic_publish_excludes_expensive_dimensions(tmp_path):
    """Regression for the critic HIGH finding: the periodic publish must not run the
    broker/llm/account-via-broker/risk dimensions (each creates a broker / pings the
    LLM). Only the cheap set + the snapshot-derived `account` may appear."""
    rt = _runtime(tmp_path)
    rt.publish_health()
    payload = json.loads((tmp_path / "steering" / "health.json").read_text())
    dims = set(payload["dimensions"])

    assert dims & _EXPENSIVE == set(), f"periodic publish leaked expensive dims: {dims & _EXPENSIVE}"
    assert _CHEAP <= dims, f"cheap dimensions missing: {_CHEAP - dims}"
    # `account` is the snapshot-derived dimension (no broker call).
    assert "account" in dims


def test_account_dimension_skipped_without_snapshot(tmp_path):
    rt = _runtime(tmp_path)
    assert rt.last_snapshot is None
    rt.publish_health()
    payload = json.loads((tmp_path / "steering" / "health.json").read_text())
    acct = payload["dimensions"]["account"]
    assert acct["status"] == "SKIPPED"
    assert acct["checks"][0]["name"] == "account_snapshot"


def test_account_dimension_derived_from_snapshot(tmp_path):
    rt = _runtime(tmp_path)
    # Mimic what publish_snapshot stores (no broker call needed here).
    rt.last_snapshot = {
        "account": {"equity": 100_000.0, "cash": 50_000.0, "invested": 50_000.0,
                    "open_pnl": 0.0, "position_count": 2},
        "market_open": True,
    }
    rt.publish_health()
    payload = json.loads((tmp_path / "steering" / "health.json").read_text())
    acct = payload["dimensions"]["account"]
    assert acct["status"] == "OK"
    detail = acct["checks"][0]["detail"]
    assert "equity=$100,000" in detail
    assert "positions=2" in detail
    assert "market=OPEN" in detail


def test_negative_cash_flags_warning(tmp_path):
    rt = _runtime(tmp_path)
    rt.last_snapshot = {
        "account": {"equity": 100.0, "cash": -500.0, "invested": 600.0,
                    "open_pnl": 0.0, "position_count": 1},
        "market_open": False,
    }
    rt.publish_health()
    payload = json.loads((tmp_path / "steering" / "health.json").read_text())
    acct = payload["dimensions"]["account"]
    names = [c["name"] for c in acct["checks"]]
    assert "account_cash_negative" in names
    # overall must reflect at least WARNING from the negative-cash flag.
    assert payload["overall"] in {"WARNING", "ERROR", "CRITICAL"}


def test_account_partial_fields_no_crash(tmp_path):
    """A snapshot with equity present but cash missing must not crash the f-string
    (the formatted branch needs BOTH fields); the dimension falls back to a plain
    'fields missing' detail and stays OK rather than being dropped from health.json."""
    rt = _runtime(tmp_path)
    rt.last_snapshot = {
        "account": {"equity": 100_000.0, "position_count": 1},  # no cash
        "market_open": True,
    }
    rt.publish_health()
    payload = json.loads((tmp_path / "steering" / "health.json").read_text())
    acct = payload["dimensions"]["account"]
    assert acct["status"] == "OK"
    assert "missing" in acct["checks"][0]["detail"].lower()


def test_publish_health_never_raises(tmp_path, monkeypatch):
    """Best-effort: an unexpected failure must not propagate (it would crash the
    scheduler job); the previous health.json is simply left in place."""
    rt = _runtime(tmp_path)
    # Force the dispatcher path to blow up.
    import src.agent.steering.runtime as rtmod
    monkeypatch.setattr(rtmod, "CheckerDispatcher",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    rt.publish_health()  # must not raise

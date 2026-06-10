"""Step 10 — daemon wiring: brief injection, steering=None fallback, config."""

from __future__ import annotations

import pandas as pd

from src.agent.executor import DecisionExecutor
from src.agent.intraday.settings import IntradayConfig
from src.agent.journal import Journal
from src.agent.steering.runtime import SteeringRuntime
from src.risk.manager import RiskManager
from src.execution.brokers.simulated_broker import SimulatedBroker
from src.trading.modes.agent import AgentTradingMode


class _Provider:
    def get_latest_price(self, symbol):
        return 100.0

    def get_bars(self, symbol, timeframe=None, limit=50):
        idx = pd.date_range("2026-05-30 09:30", periods=2, freq="5min")
        return pd.DataFrame({"open": [100, 100], "high": [101, 101], "low": [99, 99],
                             "close": [100, 100], "volume": [10, 10]}, index=idx)


class _StubOrch:
    def __init__(self):
        self.intraday_briefs: list = []

    def run_intraday(self, brief=None):
        self.intraday_briefs.append(brief)

    def run_reconcile(self, context=""):
        return "ok"

    def run_wake(self, brief, events, timeout=None):
        return "woke"


def _executor(tmp_path):
    broker = SimulatedBroker(initial_capital=100_000.0)
    broker.set_current_price("AAPL", 100.0)
    rm = RiskManager(use_bracket_orders=True)
    return DecisionExecutor(broker, rm, _Provider(), journal=Journal(root=tmp_path / "ws"),
                            universe=["AAPL"])


def test_intraday_injects_brief_when_steering_on(tmp_path):
    ex = _executor(tmp_path)
    orch = _StubOrch()
    steering = SteeringRuntime(ex, orch, steering_dir=tmp_path / "steering", token="t")
    mode = AgentTradingMode(orch, ex, steering=steering)
    steering.start()
    try:
        mode._intraday()
        assert len(orch.intraday_briefs) == 1
        assert isinstance(orch.intraday_briefs[0], str)  # a real brief, not None
    finally:
        mode.stop()


def test_intraday_legacy_when_steering_off(tmp_path):
    ex = _executor(tmp_path)
    orch = _StubOrch()
    mode = AgentTradingMode(orch, ex, steering=None)
    assert mode._wake is None and mode._news is None  # F3 inactive (NFR-8)
    mode._intraday()
    assert orch.intraday_briefs == [None]  # legacy path: no brief


def test_intraday_components_built_with_steering(tmp_path):
    ex = _executor(tmp_path)
    orch = _StubOrch()
    steering = SteeringRuntime(ex, orch, steering_dir=tmp_path / "steering", token="t")
    mode = AgentTradingMode(orch, ex, steering=steering)
    assert mode._wake is not None and mode._news is not None and mode._brief_assembler is not None


def test_intraday_config_from_mapping():
    cfg = IntradayConfig.from_mapping({
        "abnormal_move": {"atr_k": 2.0, "vol_multiple": 4.0, "atr_period": 10},
        "wake": {"detect_seconds": 7, "timeout": 90.0},
        "news": {"ttl_minutes": 20.0},
    })
    assert cfg.atr_k == 2.0 and cfg.wake_detect_seconds == 7 and cfg.news_ttl_minutes == 20.0
    assert cfg.abnormal().vol_multiple == 4.0
    # absent block -> defaults
    assert IntradayConfig.from_mapping(None).atr_k == 1.5

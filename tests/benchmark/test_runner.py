"""F70 BenchmarkRunner — isolation, fail-closed build, exception isolation.

The runner builds engines via late imports inside ``build()``, so we monkeypatch
the source-module attributes (BrokerApiBroker / TradingEngine / create_strategy).
"""
from types import SimpleNamespace

import pytest

from src.benchmark.settings import BenchmarkConfig
from src.benchmark.runner import BenchmarkRunner
from src.core.models import PortfolioState


def _pf(equity: float) -> PortfolioState:
    return PortfolioState(cash=0.0, equity=equity, positions={})


class FakeBroker:
    """Stands in for BrokerApiBroker. Raises if account_id == 'BAD'."""

    def __init__(self, *, api_key, secret_key, account_id, sandbox=True):
        if account_id == "BAD":
            raise RuntimeError("bad creds/account (fail-closed)")
        self.account_id = account_id
        self._masked_id = f"{account_id[:4]}…"

    @staticmethod
    def _mask(s, keep=8):
        return s[:keep] + "…"

    def get_portfolio_state(self):
        # equity keyed off the account so each baseline differs
        return _pf(1000.0 + len(self.account_id))


class FakeEngine:
    last_kwargs = None

    def __init__(self, **kwargs):
        FakeEngine.last_kwargs = kwargs
        self.broker = kwargs["broker"]
        self._raise = False

    def run_cycle(self):
        if self._raise:
            raise RuntimeError("cycle boom")
        return []


@pytest.fixture
def patched(monkeypatch):
    import src.execution.brokers.broker_api_broker as bap
    import src.trading.engine as eng
    import src.strategy.registry as reg

    monkeypatch.setattr(bap, "BrokerApiBroker", FakeBroker)
    monkeypatch.setattr(eng, "TradingEngine", FakeEngine)
    monkeypatch.setattr(reg, "create_strategy", lambda name, params=None: SimpleNamespace(name=name))
    FakeEngine.last_kwargs = None


def _runner(tmp_path, *, enabled=True, baselines, accounts, live="LIVE", dp="DP"):
    cfg = BenchmarkConfig(
        enabled=enabled, baselines=baselines, accounts=accounts,
        interval="eod", storage_dir=str(tmp_path),
    )
    return BenchmarkRunner(
        cfg,
        data_provider=dp,
        risk_manager="RM",
        universe=["AAPL", "MSFT"],
        broker_api_key="k", broker_api_secret="s",
        live_account_id=live,
        llm_portfolio_provider=lambda: _pf(5000.0),
    )


def test_missing_account_skipped(tmp_path, patched):
    r = _runner(tmp_path, baselines=["rsi", "macd"], accounts={"rsi": "acct-rsi"})
    built = r.build()
    assert [b.name for b in built] == ["rsi"]  # macd had no account


def test_live_account_collision_skipped(tmp_path, patched):
    r = _runner(
        tmp_path, baselines=["rsi", "macd"],
        accounts={"rsi": "LIVE", "macd": "acct-macd"}, live="LIVE",
    )
    built = r.build()
    assert [b.name for b in built] == ["macd"]  # rsi collides with live account


def test_broker_build_failure_isolated(tmp_path, patched):
    r = _runner(
        tmp_path, baselines=["rsi", "macd"],
        accounts={"rsi": "BAD", "macd": "acct-macd"},
    )
    built = r.build()
    assert [b.name for b in built] == ["macd"]  # rsi build raised -> skipped


def test_shared_data_provider(tmp_path, patched):
    r = _runner(tmp_path, baselines=["rsi"], accounts={"rsi": "acct-rsi"}, dp="SHARED_DP")
    r.build()
    assert FakeEngine.last_kwargs["data_provider"] == "SHARED_DP"


def test_tick_records_baseline_and_llm(tmp_path, patched):
    r = _runner(tmp_path, baselines=["rsi"], accounts={"rsi": "acct-rsi"})
    r.build()
    r.tick()
    assert [s.equity for s in r.recorder.load("rsi")]  # baseline recorded
    llm = r.recorder.load("llm")
    assert len(llm) == 1 and llm[0].equity == 5000.0
    assert llm[0].account_masked == "live"


def test_tick_exception_isolated(tmp_path, patched):
    r = _runner(tmp_path, baselines=["rsi"], accounts={"rsi": "acct-rsi"})
    r.build()
    r._baselines[0].engine._raise = True
    r.tick()  # must not raise
    assert r.recorder.load("rsi") == []   # failed baseline: no record this tick
    assert len(r.recorder.load("llm")) == 1  # llm still snapshotted


def test_start_noop_when_disabled(tmp_path, patched):
    r = _runner(tmp_path, enabled=False, baselines=["rsi"], accounts={"rsi": "a"})
    assert r.start() is False
    assert r._thread is None


def test_start_noop_when_no_baseline_survives(tmp_path, patched):
    r = _runner(tmp_path, baselines=["rsi"], accounts={})  # nothing mapped
    assert r.start() is False

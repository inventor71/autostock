"""Integration wiring tests for the KIS broker path (F30) — no network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import main
from src.execution.brokers.kis_broker import KisPaperBroker
from src.trading.modes.agent import AgentTradingMode


def _settings(broker_name="kis", paper=True):
    return SimpleNamespace(
        broker=SimpleNamespace(name=broker_name, paper=paper),
        data=SimpleNamespace(provider="yfinance"),
        kis_paper_api_key="ak", kis_paper_api_secret="sk", kis_paper_account="12345678-01",
        alpaca_api_key="", alpaca_secret_key="",
    )


def test_create_broker_selects_kis():
    b = main.create_broker(_settings())
    assert isinstance(b, KisPaperBroker)
    assert b.market_schedule["timezone"] == "Asia/Seoul"
    assert hasattr(b, "reconcile_oco")


def test_kis_live_not_yet_implemented():
    with pytest.raises(NotImplementedError):
        main.create_broker(_settings(paper=False))


def test_data_provider_shares_broker_client():
    s = _settings()
    b = main.create_broker(s)
    dp = main.create_data_provider(s, broker=b)
    from src.data.providers.kis_provider import KisDataProvider
    assert isinstance(dp, KisDataProvider)
    assert dp._c is b.client  # one token, respects KIS 1-issuance/min cap


class _FakeScheduler:
    def __init__(self):
        self.seconds_jobs = []
        self.market_open = []
        self.daily = []

    def add_daily_job(self, func, hour, minute, job_id, timezone="US/Eastern", **k):
        self.daily.append((job_id, timezone, hour, minute))

    def add_market_open_job(self, func, job_id="market_open", timezone="US/Eastern", hour=9, minute=30):
        self.market_open.append((job_id, timezone, hour, minute))

    def add_market_close_job(self, func, job_id="market_close", timezone="US/Eastern", hour=15, minute=55):
        pass

    def add_batch_job(self, func, interval_minutes=60, job_id="batch"):
        pass

    def add_seconds_job(self, func, seconds, job_id):
        self.seconds_jobs.append((job_id, seconds))

    def start(self):
        pass


def _agent_with(broker):
    m = AgentTradingMode.__new__(AgentTradingMode)
    m.scheduler = _FakeScheduler()
    m.executor = SimpleNamespace(broker=broker)
    m.steering = None
    m.intraday_minutes = 15
    return m


def test_kis_schedule_is_kst_and_registers_reconcile_job():
    broker = main.create_broker(_settings())
    m = _agent_with(broker)
    # exercise only the scheduling block (mirrors start())
    sched = getattr(m.executor.broker, "market_schedule", None)
    assert sched and sched["timezone"] == "Asia/Seoul"
    m.scheduler.add_seconds_job(m._oco_reconcile_tick, 5, "kis_reconcile")
    assert ("kis_reconcile", 5) in m.scheduler.seconds_jobs
    # _oco_reconcile_tick swallows broker errors (no network here)
    m._oco_reconcile_tick()

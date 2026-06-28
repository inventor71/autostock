"""F92 — broker factory provider routing. The factory is the single composition root
that maps ``broker.provider`` to a concrete broker; every account-truth path goes through
it so they all read/trade the SAME account. These tests pin the routing (network-free:
the concrete broker classes are stubbed) and guard the fail-loud on unknown providers.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.execution.brokers import factory


def _settings(*, name=None, provider="alpaca", paper=True):
    return SimpleNamespace(
        broker=SimpleNamespace(name=name, paper=paper, provider=provider),
        alpaca_api_key="ALPACA_K", alpaca_api_secret="ALPACA_S",
        broker_api_key="FARM_K", broker_api_secret="FARM_S", broker_account_id="sub-acct-1",
        kis_paper_api_key="KIS_K", kis_paper_api_secret="KIS_S", kis_paper_account="123-01",
    )


def test_selects_alpaca(monkeypatch):
    import src.execution.brokers.alpaca_broker as m
    captured = {}
    monkeypatch.setattr(m, "AlpacaBroker", lambda **kw: captured.update(kw) or "ALPACA")
    assert factory.create_broker(_settings(provider="alpaca")) == "ALPACA"
    assert captured["api_key"] == "ALPACA_K"  # alpaca creds, not farm


def test_selects_account_farm_with_subaccount(monkeypatch):
    import src.execution.brokers.account_farm_broker as m
    captured = {}
    monkeypatch.setattr(m, "AccountFarmBroker", lambda **kw: captured.update(kw) or "FARM")
    assert factory.create_broker(_settings(provider="account_farm")) == "FARM"
    # F92 regression: account_farm must use the per-instance sub-account + farm creds,
    # NOT the shared Alpaca key (the old hard-coded-AlpacaBroker bug).
    assert captured["account_id"] == "sub-acct-1"
    assert captured["api_key"] == "FARM_K"


def test_selects_kis(monkeypatch):
    import src.execution.brokers.kis.broker as m
    monkeypatch.setattr(m, "KisPaperBroker", lambda *a, **kw: "KIS")
    assert factory.create_broker(_settings(name="kis")) == "KIS"


def test_kis_live_not_yet_implemented():
    with pytest.raises(NotImplementedError):
        factory.create_broker(_settings(name="kis", paper=False))


def test_unknown_provider_fails_loud():
    # A silent fallback would trade on the wrong (Alpaca) account — must raise.
    with pytest.raises(ValueError):
        factory.create_broker(_settings(provider="robinhood"))


def test_main_reexports_factory():
    """main.create_broker stays a valid name (composition root re-export)."""
    import main
    assert main.create_broker is factory.create_broker

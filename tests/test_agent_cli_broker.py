"""F92 regression — the agent's read-only CLI tools must read the SAME account the
daemon trades, by going through the provider-aware factory. These pin the two paths
that used to hard-code AlpacaBroker (so an account_farm instance read one shared Alpaca
account instead of its own sub-account).
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace


def test_agent_tools_broker_uses_factory(monkeypatch):
    import config.config as cfg
    from src.execution.brokers import factory

    sentinel = object()
    monkeypatch.setattr(cfg, "get_settings", lambda: "SETTINGS")
    monkeypatch.setattr(factory, "create_broker", lambda s: sentinel if s == "SETTINGS" else None)

    cli = importlib.import_module("src.agent.tools.__main__")
    assert cli._broker() is sentinel


def test_equity_main_uses_factory(monkeypatch, tmp_path):
    import config.config as cfg
    from src.execution.brokers import factory
    from src.agent.logs import equity as eq

    fake_state = object()
    fake_broker = SimpleNamespace(get_portfolio_state=lambda: fake_state)
    monkeypatch.setattr(cfg, "get_settings", lambda: "SETTINGS")
    monkeypatch.setattr(factory, "create_broker", lambda s: fake_broker)

    captured = {}
    monkeypatch.setattr(eq, "record_equity", lambda state, path: captured.update(state=state, path=path))
    monkeypatch.setattr(eq, "default_path", lambda: tmp_path / "equity.jsonl")

    eq.main()
    # The snapshot recorded must come from the factory-built (provider-aware) broker.
    assert captured["state"] is fake_state

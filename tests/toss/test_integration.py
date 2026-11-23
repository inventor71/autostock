
import pytest

from config.config import Settings, _apply_env_overrides
from src.core.exceptions import BrokerError
from src.core.models import OpenOrder, Position
from src.core.types import OrderSide, OrderType
from src.execution.brokers.factory import create_broker
from src.execution.brokers.toss.credentials import save_credentials


def settings(tmp_path, credentials, **overrides):
    path = tmp_path / "private/credentials.json"
    save_credentials(credentials, path)
    values = {
        "_env_file": None, "broker": {"provider": "toss", "paper": False},
        "toss": {"credentials_file": str(path), "state_dir": str(tmp_path / "state")},
    }
    values.update(overrides)
    return Settings(**values)


def test_factory_does_not_fall_back_to_alpaca_and_shares_data_client(tmp_path, credentials):
    from main import create_data_provider
    from src.execution.brokers.toss.broker import TossBroker
    config = settings(tmp_path, credentials, data={"provider": "toss"})
    broker = create_broker(config)
    try:
        assert isinstance(broker, TossBroker)
        assert broker.client.read_only is True
        assert create_data_provider(config, broker=broker).client is broker.client
    finally:
        broker.close()


def test_toss_paper_never_maps_to_real_trading(tmp_path, credentials):
    config = settings(tmp_path, credentials, broker={"provider": "toss", "paper": True})
    with pytest.raises(ValueError, match="paper endpoint"):
        create_broker(config)


def test_toss_name_alone_never_reads_alpaca_account(tmp_path, credentials):
    config = settings(tmp_path, credentials, broker={"name": "toss", "provider": "alpaca"})
    with pytest.raises(ValueError, match="refusing an Alpaca fallback"):
        create_broker(config)


def test_health_probes_close_toss_connections(tmp_path, credentials, monkeypatch):
    from src.monitoring.health.dimensions.broker import BrokerChecker
    config = settings(tmp_path, credentials)
    clients = []

    class Broker:
        closed = False
        def is_market_open(self): return True
        def get_open_orders(self): raise BrokerError("Unavailable")
        def get_portfolio_state(self): raise BrokerError("Unavailable")
        def close(self): self.closed = True

    def factory(_):
        broker = Broker()
        clients.append(broker)
        return broker

    monkeypatch.setattr("src.execution.brokers.factory.create_broker", factory)
    assert len(BrokerChecker(config).check()) == 3
    assert len(clients) == 3 and all(c.closed for c in clients)


def test_toss_write_enable_requires_live_app_mode(tmp_path, credentials):
    config = settings(tmp_path, credentials)
    config.toss.read_only = False
    with pytest.raises(ValueError, match="app.mode=live"):
        create_broker(config)
    config.app.mode = "live"
    broker = create_broker(config)
    assert broker.client.read_only is False
    broker.close()


def test_data_only_client_never_inherits_write_permission(tmp_path, credentials):
    from main import create_data_provider
    config = settings(tmp_path, credentials, data={"provider": "toss"}, app={"mode": "live"})
    config.toss.read_only = False
    provider = create_data_provider(config)
    try:
        assert provider.client.read_only is True
    finally:
        provider.client.close()


def test_health_checks_toss_file_instead_of_alpaca_env(tmp_path, credentials):
    from src.monitoring.health.dimensions.config_env import ConfigEnvChecker
    config = settings(tmp_path, credentials, llm={"provider": "claude_code"})
    config.alpaca_api_key = config.alpaca_api_secret = ""
    result = ConfigEnvChecker(config)._check_env_vars()
    assert result.status.value == "OK"


def test_cli_uses_configured_toss_data_provider(tmp_path, credentials, monkeypatch):
    from src.agent.tools import __main__ as cli
    config = settings(tmp_path, credentials, data={"provider": "toss"})
    monkeypatch.setattr("config.config.get_settings", lambda: config)
    provider = cli._provider()
    assert provider.__class__.__name__ == "TossDataProvider"
    provider.client.close()


def test_env_overrides_do_not_treat_false_as_truthy(monkeypatch):
    monkeypatch.setenv("AUTOSTOCK_BROKER_PROVIDER", "toss")
    monkeypatch.setenv("AUTOSTOCK_BROKER_PAPER", "false")
    monkeypatch.setenv("AUTOSTOCK_TOSS_READ_ONLY", "false")
    values = {}
    _apply_env_overrides(values)
    config = Settings(_env_file=None, **values)
    assert config.broker.provider == "toss"
    assert config.broker.paper is False and config.toss.read_only is False


def test_unsupported_protection_never_cancels_existing_orders():
    from src.agent.executor import DecisionExecutor
    from src.agent.journal import Decision
    from src.risk.manager import RiskManager

    canceled = []

    class Broker:
        def get_position(self, symbol):
            return Position(symbol="AAPL", qty=10, avg_entry_price=100)
        def get_open_orders(self, symbol):
            return [OpenOrder(order_id="existing-protection", symbol="AAPL", side=OrderSide.SELL,
                              order_type=OrderType.STOP, qty=10, stop_price=90)]
        def validate_order(self, order):
            raise BrokerError("Unsupported Toss protection")
        def cancel_order(self, order_id):
            canceled.append(order_id)

    executor = DecisionExecutor.__new__(DecisionExecutor)
    executor.broker = Broker()
    executor.risk_manager = RiskManager(use_bracket_orders=True)
    with pytest.raises(BrokerError, match="Unsupported"):
        executor._place_protection(Decision(symbol="AAPL", action="ADJUST_STOP", stop=95, target=120), "ADJUST_STOP")
    assert canceled == []


def test_agent_startup_blocks_incompatible_brackets_before_models(tmp_path, credentials, monkeypatch):
    import main
    config = settings(tmp_path, credentials)
    monkeypatch.setattr(main, "create_data_provider", lambda *a, **k: pytest.fail("No agent/model startup"))
    with pytest.raises(ValueError, match="autonomous agent trading is disabled"):
        main.run_agent(config)

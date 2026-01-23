from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


CONFIG_DIR = Path(__file__).parent


class BrokerConfig(BaseModel):
    name: str = "alpaca"
    paper: bool = True


class DataConfig(BaseModel):
    provider: str = "yfinance"
    cache_dir: str = "./data"
    default_timeframe: str = "1d"


class TradingConfig(BaseModel):
    symbols: list[str] = ["AAPL", "SPY"]
    mode: str = "batch"
    batch_interval_minutes: int = 60


class RiskConfig(BaseModel):
    max_position_pct: float = 0.1
    max_portfolio_risk: float = 0.02
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.15
    max_open_positions: int = 10


class BacktestConfig(BaseModel):
    start_date: str = "2023-01-01"
    end_date: str = "2024-01-01"
    initial_capital: float = 100000.0
    commission_pct: float = 0.0


class MonitoringConfig(BaseModel):
    alerts_enabled: bool = False
    slack_webhook: str = ""
    telegram_token: str = ""
    telegram_chat_id: str = ""


class AppConfig(BaseModel):
    name: str = "autostock"
    mode: str = "paper"
    log_level: str = "INFO"


class Settings(BaseSettings):
    app: AppConfig = AppConfig()
    broker: BrokerConfig = BrokerConfig()
    data: DataConfig = DataConfig()
    trading: TradingConfig = TradingConfig()
    risk: RiskConfig = RiskConfig()
    backtest: BacktestConfig = BacktestConfig()
    monitoring: MonitoringConfig = MonitoringConfig()

    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""

    model_config = {"env_prefix": "", "env_nested_delimiter": "__"}


def load_yaml_config(path: Path) -> dict[str, Any]:
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def load_strategies_config() -> dict[str, Any]:
    return load_yaml_config(CONFIG_DIR / "strategies.yaml")


@lru_cache
def get_settings() -> Settings:
    yaml_config = load_yaml_config(CONFIG_DIR / "settings.yaml")
    return Settings(**yaml_config)

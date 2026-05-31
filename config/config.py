from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


CONFIG_DIR = Path(__file__).parent
PROJECT_ROOT = CONFIG_DIR.parent

# Which dotenv file Settings loads. Defaults to the repo-root `.env` (production), but can be
# pointed elsewhere via AUTOSTOCK_ENV_FILE — e.g. the containerized verification harness sets it to
# `.env.test` so it loads the TEST paper account and never the production `.env` (F10).
ENV_FILE = os.environ.get("AUTOSTOCK_ENV_FILE") or str(PROJECT_ROOT / ".env")


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
    # Bracket / defense-in-depth (Phase R2). Used when bracket orders are enabled.
    max_stop_distance_pct: float = 0.12  # cap how far a stop may sit from entry
    atr_stop_multiple: float = 3.0  # default stop = N x ATR when no explicit level
    market_halt_threshold_pct: float = -0.03  # halt new buys if SPY day-change <= this
    default_risk_reward: float = 2.5  # derived take-profit R:R when none given


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


class LLMConfig(BaseModel):
    provider: str = "claude"  # claude, openai
    model: str | None = None  # None uses provider default
    temperature: float = 0.3
    prompt_version: str = "latest"  # latest, best, v1, v2, etc.
    lookback_days: int = 30
    include_news: bool = True


class AgentConfig(BaseModel):
    """Agentic PM trader (`--mode agent`) settings."""

    model: str = "sonnet"  # base model for intraday / EOD turns
    research_model: str = "opus"  # deeper model for the daily research turn
    turn_timeout: float = 600.0  # seconds per intraday / EOD turn
    research_timeout: float = 1800.0  # seconds for the deep research turn (opus + web + scan)
    # Trade-ledger hygiene: ignore broker fills before the experiment began and
    # tiny test fills, so the track record reflects only the agent's trades.
    experiment_start: str | None = None  # ISO date; fills before it are dropped
    min_trade_notional: float = 0.0  # drop fills below this $ notional (penny/test)


class Settings(BaseSettings):
    app: AppConfig = AppConfig()
    broker: BrokerConfig = BrokerConfig()
    data: DataConfig = DataConfig()
    trading: TradingConfig = TradingConfig()
    risk: RiskConfig = RiskConfig()
    backtest: BacktestConfig = BacktestConfig()
    monitoring: MonitoringConfig = MonitoringConfig()
    llm: LLMConfig = LLMConfig()
    agent: AgentConfig = AgentConfig()
    # F3 intraday redesign tunables (abnormal_move / wake / news / bars / price).
    # Raw mapping -> IntradayConfig.from_mapping at the composition root.
    intraday: dict = {}

    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    model_config = {
        "env_prefix": "",
        "env_nested_delimiter": "__",
        "env_file": ENV_FILE,
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


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

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from config.config import get_settings, load_strategies_config
from src.monitoring.logger import setup_logging


def create_data_provider(settings):
    """Create data provider based on config."""
    if settings.data.provider == "alpaca":
        from src.data.providers.alpaca_provider import AlpacaDataProvider
        return AlpacaDataProvider(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
        )
    else:
        from src.data.providers.yfinance_provider import YFinanceProvider
        return YFinanceProvider()


def create_broker(settings):
    """Create broker based on config."""
    from src.execution.brokers.alpaca_broker import AlpacaBroker
    return AlpacaBroker(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key,
        paper=settings.broker.paper,
    )


def create_strategies(strategies_config: dict):
    """Create strategy instances from config."""
    # Import strategies to trigger registration
    import src.strategy.technical.ma_crossover
    import src.strategy.technical.rsi_strategy
    import src.strategy.technical.macd_strategy
    import src.strategy.technical.bollinger
    import src.strategy.ml.rf_strategy
    import src.strategy.ml.lstm_strategy
    import src.strategy.ensemble.voting
    import src.strategy.ensemble.weighted

    from src.strategy.registry import create_strategy

    active = strategies_config.get("active_strategies", [])
    strategy_defs = strategies_config.get("strategies", {})

    strategies = []
    for name in active:
        if name in strategy_defs:
            params = strategy_defs[name].get("params", {})
            try:
                strategy = create_strategy(name, params)
                strategies.append(strategy)
                logger.info(f"Loaded strategy: {name}")
            except Exception as e:
                logger.error(f"Failed to load strategy '{name}': {e}")
        else:
            logger.warning(f"Strategy '{name}' not found in config")

    return strategies


def run_backtest(settings, strategies_config: dict) -> None:
    """Run backtest mode."""
    from datetime import datetime
    from src.backtest.engine import BacktestEngine

    strategies = create_strategies(strategies_config)
    if not strategies:
        logger.error("No strategies configured")
        return

    data_provider = create_data_provider(settings)
    risk_config = settings.risk.model_dump()

    for symbol in settings.trading.symbols:
        logger.info(f"Backtesting {symbol}...")
        bars = data_provider.get_bars(
            symbol=symbol,
            start=datetime.fromisoformat(settings.backtest.start_date),
            end=datetime.fromisoformat(settings.backtest.end_date),
        )

        for strategy in strategies:
            engine = BacktestEngine(
                strategy=strategy,
                initial_capital=settings.backtest.initial_capital,
                commission_pct=settings.backtest.commission_pct,
                risk_config=risk_config,
            )
            result = engine.run(symbol, bars)
            print(f"\n{'='*50}")
            print(f"Strategy: {result.strategy_name} | Symbol: {symbol}")
            print(f"Period: {settings.backtest.start_date} to {settings.backtest.end_date}")
            print(f"{'='*50}")
            print(f"Total Return: {result.total_return_pct:.2f}%")
            print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
            print(f"Max Drawdown: {result.max_drawdown_pct:.2f}%")
            print(f"Total Trades: {result.total_trades}")
            print(f"Win Rate: {result.win_rate:.1%}")
            print(f"Profit Factor: {result.profit_factor:.2f}")
            print(f"Final Capital: ${result.final_capital:,.2f}")


def run_paper(settings, strategies_config: dict) -> None:
    """Run paper trading mode."""
    from src.core.types import TimeFrame
    from src.risk.manager import RiskManager
    from src.trading.engine import TradingEngine
    from src.trading.modes.batch import BatchTradingMode

    strategies = create_strategies(strategies_config)
    if not strategies:
        logger.error("No strategies configured")
        return

    data_provider = create_data_provider(settings)
    broker = create_broker(settings)
    risk_manager = RiskManager(
        max_position_pct=settings.risk.max_position_pct,
        max_portfolio_risk=settings.risk.max_portfolio_risk,
        stop_loss_pct=settings.risk.stop_loss_pct,
        take_profit_pct=settings.risk.take_profit_pct,
        max_open_positions=settings.risk.max_open_positions,
    )

    engine = TradingEngine(
        data_provider=data_provider,
        broker=broker,
        strategies=strategies,
        risk_manager=risk_manager,
        symbols=settings.trading.symbols,
        timeframe=TimeFrame(settings.data.default_timeframe),
    )

    if settings.trading.mode == "realtime":
        from src.trading.modes.realtime import RealtimeTradingMode
        mode = RealtimeTradingMode(
            engine=engine,
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            paper=settings.broker.paper,
        )
    else:
        mode = BatchTradingMode(
            engine=engine,
            interval_minutes=settings.trading.batch_interval_minutes,
        )

    logger.info(f"Starting {settings.trading.mode} trading mode...")
    mode.start()


def main():
    parser = argparse.ArgumentParser(description="Autostock - Automated Trading System")
    parser.add_argument(
        "--mode",
        choices=["backtest", "paper", "live"],
        default=None,
        help="Trading mode (overrides config)",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Symbols to trade (overrides config)",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Log level (overrides config)",
    )
    args = parser.parse_args()

    settings = get_settings()
    strategies_config = load_strategies_config()

    # Override settings with CLI args
    mode = args.mode or settings.app.mode
    log_level = args.log_level or settings.app.log_level
    if args.symbols:
        settings.trading.symbols = args.symbols

    setup_logging(level=log_level, log_file="logs/autostock.log")
    logger.info(f"Autostock starting in {mode} mode")

    if mode == "backtest":
        run_backtest(settings, strategies_config)
    elif mode in ("paper", "live"):
        run_paper(settings, strategies_config)
    else:
        logger.error(f"Unknown mode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()

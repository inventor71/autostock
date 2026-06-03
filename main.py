from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from config.config import get_settings, load_strategies_config
from src.monitoring.logger import setup_logging
from src.universe.factory import resolve_universe


def create_data_provider(settings, broker=None):
    """Create data provider based on config. A KIS broker shares its REST client
    (so both honour one token, respecting KIS's 1-issuance/min cap)."""
    if (settings.broker.name or "").lower() == "kis" or settings.data.provider == "kis":
        from src.data.providers.kis_provider import KisDataProvider
        client = getattr(broker, "client", None)
        if client is not None:
            return KisDataProvider("", "", client=client)
        return KisDataProvider(
            settings.kis_paper_api_key, settings.kis_paper_api_secret,
            paper=settings.broker.paper)
    if settings.data.provider == "alpaca":
        from src.data.providers.alpaca_provider import AlpacaDataProvider
        return AlpacaDataProvider(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_api_secret,
        )
    else:
        from src.data.providers.yfinance_provider import YFinanceProvider
        return YFinanceProvider()


def create_broker(settings):
    """Create broker based on config (alpaca | kis | broker_api)."""
    if (settings.broker.name or "").lower() == "kis":
        if not settings.broker.paper:
            raise NotImplementedError("KIS live broker not yet implemented (paper only)")
        from src.execution.brokers.kis_broker import KisPaperBroker
        return KisPaperBroker(
            settings.kis_paper_api_key, settings.kis_paper_api_secret,
            settings.kis_paper_account, paper=True,
        )
    provider = settings.broker.provider
    if provider == "broker_api":
        from src.execution.brokers.broker_api_broker import BrokerApiBroker
        return BrokerApiBroker(
            api_key=settings.broker_api_key,
            secret_key=settings.broker_api_secret,
            account_id=settings.broker_account_id,
            sandbox=True,
        )
    # default: alpaca (Trading API)
    from src.execution.brokers.alpaca_broker import AlpacaBroker
    return AlpacaBroker(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_api_secret,
        paper=settings.broker.paper,
    )


def _resolve_api_key(settings, provider: str) -> str:
    """Resolve the API key for an LLM provider from settings (composition root)."""
    if provider == "claude":
        return settings.anthropic_api_key
    if provider == "openai":
        return settings.openai_api_key
    return ""  # e.g. claude_code uses the logged-in CLI session, no key


def _llm_params(settings) -> dict:
    """The llm.* config + resolved api key, injected into the LLM strategy's params
    so the strategy never reaches into the global settings itself."""
    provider = settings.llm.provider
    return {
        "provider": provider,
        "model": settings.llm.model,
        "temperature": settings.llm.temperature,
        "prompt_version": settings.llm.prompt_version,
        "lookback_days": settings.llm.lookback_days,
        "include_news": settings.llm.include_news,
        "api_key": _resolve_api_key(settings, provider),
    }


def create_strategies(strategies_config: dict, settings):
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
    import src.strategy.llm.llm_strategy

    from src.strategy.registry import create_strategy

    active = strategies_config.get("active_strategies", [])
    strategy_defs = strategies_config.get("strategies", {})

    strategies = []
    for name in active:
        if name in strategy_defs:
            params = strategy_defs[name].get("params", {})
            if name == "llm":
                # Inject configured llm.* + api_key; strategies.yaml params override.
                params = {**_llm_params(settings), **params}
            try:
                strategy = create_strategy(name, params)
                strategies.append(strategy)
                logger.info(f"Loaded strategy: {name}")
            except Exception as e:
                logger.error(f"Failed to load strategy '{name}': {e}")
        else:
            logger.warning(f"Strategy '{name}' not found in config")

    return strategies


def run_backtest(
    settings,
    strategies_config: dict,
    improve_prompt: bool = False,
    improvement_iterations: int = 1,
) -> None:
    """Run backtest mode.

    Args:
        settings: Application settings.
        strategies_config: Strategy configuration dict.
        improve_prompt: Whether to run prompt auto-improvement after backtest.
        improvement_iterations: Number of improvement iterations to run.
    """
    from datetime import datetime
    from src.backtest.engine import BacktestEngine
    from src.core.models import BacktestResult

    strategies = create_strategies(strategies_config, settings)
    if not strategies:
        logger.error("No strategies configured")
        return

    data_provider = create_data_provider(settings)
    risk_config = settings.risk.model_dump()

    # Load market data for entire universe
    universe = resolve_universe(settings)
    logger.info(f"Loading market data for {len(universe)} symbols...")
    bars_dict = {}
    for symbol in universe:
        try:
            bars = data_provider.get_bars(
                symbol=symbol,
                start=datetime.fromisoformat(settings.backtest.start_date),
                end=datetime.fromisoformat(settings.backtest.end_date),
            )
            bars_dict[symbol] = bars
            logger.debug(f"Loaded {len(bars)} bars for {symbol}")
        except Exception as e:
            logger.warning(f"Failed to load data for {symbol}: {e}")

    if not bars_dict:
        logger.error("No market data loaded")
        return

    logger.info(f"Loaded data for {len(bars_dict)} symbols")

    # Collect results for LLM strategies (for potential improvement)
    llm_results: list[BacktestResult] = []

    for strategy in strategies:
        engine = BacktestEngine(
            strategy=strategy,
            initial_capital=settings.backtest.initial_capital,
            commission_pct=settings.backtest.commission_pct,
            risk_config=risk_config,
        )

        # Run backtest with full universe
        result = engine.run(list(bars_dict.keys()), bars_dict)

        print(f"\n{'='*50}")
        print(f"Strategy: {result.strategy_name} | Universe: {len(bars_dict)} symbols")
        print(f"Period: {settings.backtest.start_date} to {settings.backtest.end_date}")
        print(f"{'='*50}")
        print(f"Total Return: {result.total_return_pct:.2f}%")
        print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
        print(f"Max Drawdown: {result.max_drawdown_pct:.2f}%")
        print(f"Total Trades: {result.total_trades}")
        print(f"Win Rate: {result.win_rate:.1%}")
        print(f"Profit Factor: {result.profit_factor:.2f}")
        print(f"Final Capital: ${result.final_capital:,.2f}")

        # Collect LLM strategy results for improvement
        if result.strategy_name == "llm":
            llm_results.append(result)

    # Run prompt auto-improvement if requested
    if improve_prompt and llm_results:
        _run_prompt_improvement(settings, llm_results, improvement_iterations)


def _run_prompt_improvement(
    settings,
    backtest_results: list,
    iterations: int = 1,
) -> None:
    """Run prompt auto-improvement cycle.

    Args:
        settings: Application settings.
        backtest_results: List of BacktestResult from LLM strategy.
        iterations: Number of improvement iterations.
    """
    from src.strategy.llm.prompt_manager import PromptManager
    from src.strategy.llm.auto_improver import PromptAutoImprover

    logger.info(f"Starting prompt auto-improvement ({iterations} iteration(s))...")

    prompt_manager = PromptManager()
    improver = PromptAutoImprover(
        prompt_manager=prompt_manager,
        provider=settings.llm.provider,
        api_key=_resolve_api_key(settings, settings.llm.provider),
    )

    # Record current results
    current_version = settings.llm.prompt_version
    if current_version == "latest":
        current_prompt = prompt_manager.get_prompt("latest")
        if current_prompt:
            current_version = current_prompt.version
        else:
            current_version = "v1"

    # Record backtest results for current version
    for result in backtest_results:
        prompt_manager.record_backtest_result(current_version, result)

    # Run improvement iterations
    version = current_version
    for i in range(iterations):
        logger.info(f"Improvement iteration {i + 1}/{iterations}")

        new_version = improver.analyze_and_improve(version, backtest_results)
        if new_version is None:
            logger.warning(f"Improvement iteration {i + 1} failed to generate new prompt")
            break

        print(f"\n{'='*50}")
        print(f"Created improved prompt: {new_version.version}")
        print(f"Parent version: {version}")
        if new_version.improvement_notes:
            print(f"Changes:\n{new_version.improvement_notes}")
        print(f"{'='*50}")

        version = new_version.version

    # Show version comparison
    if version != current_version:
        comparison = prompt_manager.compare_versions(current_version, version)
        print(f"\nVersion Comparison ({current_version} -> {version}):")
        print(f"  Note: Re-run backtest with new prompt to see actual improvement")


def run_paper(settings, strategies_config: dict) -> None:
    """Run paper trading mode."""
    from src.core.types import TimeFrame, timeframe_from_minutes
    from src.risk.manager import RiskManager
    from src.trading.engine import TradingEngine
    from src.trading.modes.batch import BatchTradingMode

    strategies = create_strategies(strategies_config, settings)
    if not strategies:
        logger.error("No strategies configured")
        return

    broker = create_broker(settings)
    data_provider = create_data_provider(settings, broker=broker)
    risk_manager = RiskManager(
        max_position_pct=settings.risk.max_position_pct,
        max_portfolio_risk=settings.risk.max_portfolio_risk,
        stop_loss_pct=settings.risk.stop_loss_pct,
        take_profit_pct=settings.risk.take_profit_pct,
        max_open_positions=settings.risk.max_open_positions,
        max_stop_distance_pct=settings.risk.max_stop_distance_pct,
        atr_stop_multiple=settings.risk.atr_stop_multiple,
        market_halt_threshold_pct=settings.risk.market_halt_threshold_pct,
        default_risk_reward=settings.risk.default_risk_reward,
        shorting_enabled=settings.risk.shorting_enabled,
        short_market_halt_threshold_pct=settings.risk.short_market_halt_threshold_pct,
        individual_stock_halt_pct=settings.risk.individual_stock_halt_pct,
        short_stop_loss_pct=settings.risk.short_stop_loss_pct,
        short_take_profit_pct=settings.risk.short_take_profit_pct,
        short_max_stop_distance_pct=settings.risk.short_max_stop_distance_pct,
    )

    # In batch mode the bar timeframe must align with how often the cycle runs:
    # a 5-minute interval should evaluate 5-minute bars, not re-read the same
    # daily bar. Realtime mode keeps the configured default_timeframe.
    if settings.trading.mode == "batch":
        interval = settings.trading.batch_interval_minutes
        timeframe = timeframe_from_minutes(interval)
        if timeframe.minutes != interval:
            logger.warning(
                f"batch_interval_minutes={interval} has no exact bar timeframe; "
                f"using nearest supported timeframe {timeframe.value} "
                f"({timeframe.minutes}min) for OHLCV bars"
            )
        else:
            logger.info(
                f"Batch mode: fetching {timeframe.value} bars to match "
                f"{interval}min interval"
            )
    else:
        timeframe = TimeFrame(settings.data.default_timeframe)

    engine = TradingEngine(
        data_provider=data_provider,
        broker=broker,
        strategies=strategies,
        risk_manager=risk_manager,
        universe=resolve_universe(settings, client=getattr(broker, "client", None)),
        timeframe=timeframe,
    )

    if settings.trading.mode == "realtime":
        from src.trading.modes.realtime import RealtimeTradingMode
        mode = RealtimeTradingMode(
            engine=engine,
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_api_secret,
            paper=settings.broker.paper,
        )
    else:
        mode = BatchTradingMode(
            engine=engine,
            interval_minutes=settings.trading.batch_interval_minutes,
        )

    logger.info(f"Starting {settings.trading.mode} trading mode...")
    mode.start()


def _make_signal_brief_provider(settings, data_provider, broker):
    """F61: build the callable that returns the market-signal brief text (or None).

    Best-effort and fail-honest: if signals are disabled or wiring fails, return
    None so the research turn runs exactly as before."""
    from src.signals.settings import SignalsConfig

    cfg = SignalsConfig.from_settings(settings.signals)
    if not cfg.enabled:
        return None
    try:
        from src.signals.brief import to_prompt_text
        from src.signals.collector import SignalCollector

        def _held() -> list[str]:
            return sorted(broker.get_portfolio_state().positions.keys())

        collector = SignalCollector.from_settings(
            price_provider=data_provider, held_provider=_held
        )

        def _brief() -> str | None:
            return to_prompt_text(collector.collect()) or None

        return _brief
    except Exception as exc:  # never let signal wiring break agent startup
        logger.warning("signal brief provider unavailable: {}", exc)
        return None


def run_agent(settings, fresh: bool = False, steering: bool = False) -> None:
    """Run the agentic PM trading loop: the LLM agent writes the journal, the
    executor trades its decisions through RiskManager (bracket orders) -> Broker.

    ``fresh`` forces a clean session on launch (otherwise a same-day restart
    resumes today's session)."""
    from src.agent.executor import DecisionExecutor
    from src.agent.orchestrator import AgentTradingLoop
    from src.agent.session import AgentSession
    from src.risk.manager import RiskManager
    from src.trading.modes.agent import AgentTradingMode

    broker = create_broker(settings)
    data_provider = create_data_provider(settings, broker=broker)
    risk_manager = RiskManager(
        max_position_pct=settings.risk.max_position_pct,
        max_portfolio_risk=settings.risk.max_portfolio_risk,
        stop_loss_pct=settings.risk.stop_loss_pct,
        take_profit_pct=settings.risk.take_profit_pct,
        max_open_positions=settings.risk.max_open_positions,
        max_stop_distance_pct=settings.risk.max_stop_distance_pct,
        atr_stop_multiple=settings.risk.atr_stop_multiple,
        market_halt_threshold_pct=settings.risk.market_halt_threshold_pct,
        default_risk_reward=settings.risk.default_risk_reward,
        shorting_enabled=settings.risk.shorting_enabled,
        short_market_halt_threshold_pct=settings.risk.short_market_halt_threshold_pct,
        individual_stock_halt_pct=settings.risk.individual_stock_halt_pct,
        short_stop_loss_pct=settings.risk.short_stop_loss_pct,
        short_take_profit_pct=settings.risk.short_take_profit_pct,
        short_max_stop_distance_pct=settings.risk.short_max_stop_distance_pct,
        use_bracket_orders=True,
    )

    universe = resolve_universe(settings, client=getattr(broker, "client", None))
    session = AgentSession(model=settings.agent.model, timeout=settings.agent.turn_timeout)
    research_signals = settings.research.get("signals") if settings.research else None
    reflection_cfg = settings.research.get("reflection", {}) if settings.research else {}

    # F61: market-signal brief — assembled fresh each research turn and prepended
    # to the prompt. Best-effort; any wiring failure leaves the agent unaffected.
    signal_brief_provider = _make_signal_brief_provider(settings, data_provider, broker)

    orchestrator = AgentTradingLoop(
        session=session,
        universe=universe,
        portfolio_provider=broker.get_portfolio_state,
        research_model=settings.agent.research_model,
        research_timeout=settings.agent.research_timeout,
        multi_agent_enabled=settings.multi_agent.enabled,
        multi_agent_mode=settings.multi_agent.mode,
        multi_agent_n=settings.multi_agent.n_agents,
        research_signals=research_signals,
        reflection_enabled=reflection_cfg.get("enabled", True),
        reflection_max_lessons=reflection_cfg.get("max_lessons_injected", 10),
        shorting_enabled=settings.risk.shorting_enabled,
        signal_brief_provider=signal_brief_provider,
    )
    executor = DecisionExecutor(
        broker, risk_manager, data_provider, journal=session.journal, universe=universe
    )
    logger.info(f"Agent mode: {len(universe)} symbols, broker paper={settings.broker.paper}")

    steering_runtime = None
    if steering:
        from src.agent.steering.runtime import SteeringRuntime
        # Settings reads .env via pydantic (extra="ignore"), so a non-field var like
        # STEERING_OPERATOR_TOKEN never lands in os.environ. Load .env into the process
        # env here so the daemon and the separately-launched console can share ONE token
        # (SteeringRuntime honors os.environ[STEERING_OPERATOR_TOKEN]); load_dotenv does
        # NOT override an already-exported value, so an operator-set token still wins.
        from dotenv import load_dotenv
        load_dotenv()
        steering_runtime = SteeringRuntime(executor, orchestrator)
        logger.info(
            "Human steering enabled: operator console talks to the daemon via the "
            "file-drop channel at {} (agent confined by PreToolUse hook).",
            steering_runtime.steering_dir,
        )

    from src.agent.intraday.settings import IntradayConfig

    AgentTradingMode(
        orchestrator, executor,
        intraday_minutes=settings.trading.batch_interval_minutes,
        experiment_start=settings.agent.experiment_start,
        min_trade_notional=settings.agent.min_trade_notional,
        steering=steering_runtime,
        intraday_config=IntradayConfig.from_mapping(settings.intraday),
    ).start(fresh=fresh)


def main():
    parser = argparse.ArgumentParser(description="Autostock - Automated Trading System")
    parser.add_argument(
        "--mode",
        choices=["backtest", "paper", "live", "agent"],
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
    parser.add_argument(
        "--improve-prompt",
        action="store_true",
        help="Run LLM prompt auto-improvement after backtest (requires 'llm' strategy)",
    )
    parser.add_argument(
        "--improvement-iterations",
        type=int,
        default=1,
        help="Number of prompt improvement iterations (default: 1)",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Agent mode: start a clean session instead of resuming today's",
    )
    parser.add_argument(
        "--steering",
        action="store_true",
        help="Agent mode: enable the human steering console (file-drop channel "
             "at steering/; operator tool sends commands, daemon stays confined)",
    )
    args = parser.parse_args()

    settings = get_settings()
    strategies_config = load_strategies_config()

    # Override settings with CLI args
    mode = args.mode or settings.app.mode
    log_level = args.log_level or settings.app.log_level
    if args.symbols:
        # --symbols overrides the resolved universe for every run mode.
        settings.universe = {**(settings.universe or {}), "override": args.symbols}

    setup_logging(level=log_level, log_file="logs/autostock.log")
    logger.info(f"Autostock starting in {mode} mode")

    if mode == "backtest":
        run_backtest(
            settings,
            strategies_config,
            improve_prompt=args.improve_prompt,
            improvement_iterations=args.improvement_iterations,
        )
    elif mode in ("paper", "live"):
        run_paper(settings, strategies_config)
    elif mode == "agent":
        run_agent(settings, fresh=args.fresh, steering=args.steering)
    else:
        logger.error(f"Unknown mode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()

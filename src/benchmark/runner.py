from __future__ import annotations

import threading
from typing import Callable

from loguru import logger

from src.core.models import PortfolioState
from src.core.types import TimeFrame
from src.benchmark.config import BenchmarkConfig
from src.benchmark.models import LLM_KEY
from src.benchmark.store import EquityRecorder


def _import_baseline_strategies() -> None:
    """Trigger registry registration for every baseline strategy class."""
    import src.strategy.buy_and_hold  # noqa: F401
    import src.strategy.technical.bollinger  # noqa: F401
    import src.strategy.technical.ma_crossover  # noqa: F401
    import src.strategy.technical.macd_strategy  # noqa: F401
    import src.strategy.technical.rsi_strategy  # noqa: F401


class _Baseline:
    """One baseline: its name, the engine that trades it, and the masked account."""

    def __init__(self, name: str, engine, account_masked: str):
        self.name = name
        self.engine = engine
        self.account_masked = account_masked


class BenchmarkRunner:
    """Runs baseline strategies as shadow paper portfolios on dedicated sandbox
    accounts, recording their equity alongside the live LLM account.

    Isolation is structural (NFR-1): baselines only ever touch the sandbox account
    ids in ``config.accounts``; a baseline whose account is missing, un-buildable,
    or collides with the live account is skipped (fail-closed). The runner shares
    the live ``data_provider`` (no duplicate market-data fetch, NFR-2) and runs on
    its own background thread so it can never block the agent loop.
    """

    def __init__(
        self,
        config: BenchmarkConfig,
        *,
        data_provider,
        risk_manager,
        universe: list[str],
        broker_api_key: str,
        broker_api_secret: str,
        live_account_id: str,
        llm_portfolio_provider: Callable[[], PortfolioState],
        timeframe: TimeFrame = TimeFrame.DAY_1,
        strategy_params: dict[str, dict] | None = None,
    ):
        self.config = config
        self.data_provider = data_provider
        self.risk_manager = risk_manager
        self.universe = universe
        self.broker_api_key = broker_api_key
        self.broker_api_secret = broker_api_secret
        self.live_account_id = str(live_account_id or "")
        self.llm_portfolio_provider = llm_portfolio_provider
        self.timeframe = timeframe
        self.strategy_params = strategy_params or {}

        self.recorder = EquityRecorder(config.storage_dir)
        self._baselines: list[_Baseline] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ── build ────────────────────────────────────────────────────────────────

    def build(self) -> list[_Baseline]:
        """Assemble one engine per baseline, fail-closed on any account problem."""
        from src.execution.brokers.broker_api_broker import BrokerApiBroker
        from src.strategy.registry import create_strategy
        from src.trading.engine import TradingEngine

        _import_baseline_strategies()
        self._baselines = []

        for name in self.config.baselines:
            if name == LLM_KEY:
                logger.error(
                    "benchmark: baseline named '{}' collides with the reserved live "
                    "equity series key — skipped", LLM_KEY,
                )
                continue
            account_id = self.config.accounts.get(name)
            if not account_id:
                logger.warning("benchmark: '{}' has no sandbox account — skipped", name)
                continue
            if self.live_account_id and str(account_id) == self.live_account_id:
                logger.error(
                    "benchmark: '{}' account collides with the LIVE account — skipped "
                    "(production isolation, NFR-1)", name,
                )
                continue
            try:
                broker = BrokerApiBroker(
                    api_key=self.broker_api_key,
                    secret_key=self.broker_api_secret,
                    account_id=str(account_id),
                    sandbox=True,
                )
                strategy = create_strategy(name, self.strategy_params.get(name, {}))
                engine = TradingEngine(
                    data_provider=self.data_provider,
                    broker=broker,
                    strategies=[strategy],
                    risk_manager=self.risk_manager,
                    universe=self.universe,
                    timeframe=self.timeframe,
                )
                masked = getattr(broker, "_masked_id", None) or BrokerApiBroker._mask(str(account_id))
                self._baselines.append(_Baseline(name, engine, masked))
                logger.info("benchmark: '{}' ready (account {})", name, masked)
            except Exception as exc:  # BrokerError (bad creds/account) or build error
                logger.error("benchmark: '{}' build failed — skipped: {}", name, exc)
        return self._baselines

    # ── tick ───────────────────────────────────────────────────────────────--

    def tick(self) -> None:
        """One benchmark cycle: trade each baseline, snapshot all equities.

        Exceptions are isolated per baseline (BR-4) and never propagate — the
        agent daemon must be unaffected by a benchmark hiccup.
        """
        for b in self._baselines:
            try:
                b.engine.run_cycle()
                portfolio = b.engine.broker.get_portfolio_state()
                self.recorder.record(b.name, portfolio, b.account_masked)
            except Exception as exc:
                logger.warning("benchmark: tick failed for '{}': {}", b.name, exc)
        # LLM account equity — same schema, same tick (the comparison baseline).
        try:
            llm_portfolio = self.llm_portfolio_provider()
            self.recorder.record(LLM_KEY, llm_portfolio, account_masked="live")
        except Exception as exc:
            logger.warning("benchmark: failed to snapshot LLM equity: {}", exc)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def _interval_seconds(self) -> float:
        minutes = self.config.interval_minutes
        return minutes * 60.0 if minutes else 24 * 60 * 60.0  # EOD ≈ daily

    def _loop(self) -> None:
        interval = self._interval_seconds()
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(interval)

    def start(self) -> bool:
        """Start the background loop. No-op (returns False) if disabled or no
        baseline survived the fail-closed build."""
        if not self.config.enabled:
            logger.info("benchmark: disabled — not starting")
            return False
        self.build()
        if not self._baselines:
            logger.warning("benchmark: no baseline available after build — not starting")
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="benchmark", daemon=True)
        self._thread.start()
        logger.info(
            "benchmark: started with {} baselines, cadence={}",
            len(self._baselines), self.config.interval,
        )
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

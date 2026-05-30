"""Agent trading mode: the full PM loop (brain + body) on a market-aware schedule.

Composes the slow-loop orchestrator (the LLM PM agent writing the journal) with
the decision executor (trading via RiskManager -> Broker). Research is decoupled
from execution by the clock: the agent may **research ahead** (pre-market), but
the executor only places orders during the **regular session** (it defers when
closed, leaving decisions pending for the open).

Schedule (ET): pre-market research ~09:00 -> execute at the 09:30 open ->
intraday turns every N min (skipped when the market is closed) -> EOD review at
15:55. On start it researches immediately (and executes if already open).
"""

from __future__ import annotations

import time

from loguru import logger

from src.agent.executor import DecisionExecutor
from src.agent.orchestrator import AgentTradingLoop
from src.trading.scheduler import TradingScheduler


class AgentTradingMode:
    def __init__(
        self,
        orchestrator: AgentTradingLoop,
        executor: DecisionExecutor,
        intraday_minutes: int = 15,
        research_hour: int = 9,
        research_minute: int = 0,
        experiment_start: str | None = None,
        min_trade_notional: float = 0.0,
        steering=None,
        intraday_config=None,
    ):
        self.orchestrator = orchestrator
        self.executor = executor
        self.intraday_minutes = intraday_minutes
        self.research_hour = research_hour
        self.research_minute = research_minute
        # Optional F4 SteeringRuntime. When present, all executor work funnels
        # through its single CommandBus worker and all LLM turns go through its
        # TurnCoordinator; when None, the loop behaves exactly as before (NFR-8).
        self.steering = steering
        # Trade-ledger hygiene (injected from config by the composition root):
        # drop fills before the experiment began and tiny test/penny fills.
        self.experiment_start = experiment_start
        self.min_trade_notional = min_trade_notional
        self.scheduler = TradingScheduler()
        # Tell the agent subprocess which journal root to write watch.jsonl to, so
        # the `watch` tool and the daemon's WatchStore never split on a non-default
        # workspace (review #5). Inherited via session._invoke's env copy.
        journal = getattr(self.executor, "journal", None)
        if journal is not None:
            import os
            os.environ["AGENT_JOURNAL_ROOT"] = str(journal.root)
        # F3 intraday redesign: brief assembly + event-driven wakes + news diff.
        # Active ONLY with steering (it reads the snapshot/RunState/ReconcileWorker);
        # without steering, _intraday falls back to the legacy prompt (NFR-8).
        from src.agent.intraday.settings import IntradayConfig
        self.intraday_config = intraday_config or IntradayConfig()
        self._brief_assembler = None
        self._wake = None
        self._news = None
        self._watch = None
        if self.steering is not None:
            self._setup_intraday()

    # ------------------------------------------------------------------ #
    # F3 intraday redesign (only constructed when steering is enabled)
    # ------------------------------------------------------------------ #
    def _setup_intraday(self) -> None:
        from src.agent.intraday.bars import BarCache
        from src.agent.intraday.brief import BriefAssembler
        from src.agent.intraday.news_diff import NewsPoller
        from src.agent.intraday.wake import WakeDetector
        from src.agent.intraday.watch_store import WatchStore

        cfg = self.intraday_config
        root = self.executor.journal.root
        bar_cache = BarCache(self.executor.data_provider,
                             bars_ttl=cfg.bars_cache_seconds, price_ttl=cfg.price_cache_seconds)
        self._watch = WatchStore(root)
        self._brief_assembler = BriefAssembler(
            bar_cache, state=self.steering.state, watch_store=self._watch)
        self._news = NewsPoller(self._news_provider(), root,
                                ttl_minutes=cfg.news_ttl_minutes,
                                symbols_fn=self._intraday_symbols)
        self._wake = WakeDetector(
            snapshot_fn=lambda: self.steering.last_snapshot,
            state=self.steering.state, watch_store=self._watch, bar_cache=bar_cache,
            reconcile_worker=self.steering.reconcile_worker, wake_runner=self._wake_runner,
            config=cfg.abnormal(), wake_timeout=cfg.wake_timeout)

    @staticmethod
    def _news_provider():
        from src.data.providers.news_provider import YFinanceNewsProvider
        return YFinanceNewsProvider()

    def _intraday_symbols(self) -> list[str]:
        from src.agent.intraday.util import held_and_watched
        snap = self.steering.last_snapshot if self.steering else None
        return held_and_watched(snap, self._watch)

    def _brief(self, *, include_news: bool) -> str:
        snap = self.steering.last_snapshot if self.steering else None
        news = None
        if include_news and self._news is not None:
            news = self._news.diff_for(self._intraday_symbols())
        return self._brief_assembler.build(snapshot=snap, news=news, include_news=include_news)

    def _wake_runner(self, events):
        """Fire one coalesced wake turn (runs inside the ReconcileWorker's
        reconcile_turn, i.e. already under turn_lock). News is excluded from wake
        briefs (it rides the scheduled turn)."""
        brief = self._brief(include_news=False)
        return self.orchestrator.run_wake(brief, events, timeout=self.intraday_config.wake_timeout)

    # ------------------------------------------------------------------ #
    # Steering helpers (no-ops when steering is disabled)
    # ------------------------------------------------------------------ #
    def _paused(self) -> bool:
        return self.steering is not None and self.steering.state.run_state().paused

    def _funnel(self, fn, timeout: float = 180.0):
        """Run executor work on the single CommandBus worker when steering is on
        (so console mutations and scheduled execution never race the broker/cursor,
        BR-7.1'); otherwise call it directly."""
        if self.steering is not None:
            return self.steering.bus.submit_and_wait(fn, timeout=timeout)
        return fn()

    def _scheduled_turn(self, run_fn) -> bool:
        """Run a scheduled LLM turn via the TurnCoordinator (skip-if-busy) when
        steering is on; else run directly. Returns whether it ran."""
        if self.steering is not None:
            status, _ = self.steering.coordinator.try_scheduled_turn(run_fn)
            if status != "ran":
                logger.info("scheduled turn skipped ({})", _)
            return status == "ran"
        run_fn()
        return True

    def _exec_pending_and_exits(self) -> None:
        self.executor.execute_pending()
        self.executor.run_risk_exits()

    # ------------------------------------------------------------------ #
    # Cycles
    # ------------------------------------------------------------------ #
    def _premarket_research(self) -> None:
        """Deep research turn — may run pre-market; writes decisions only."""
        if self._paused():
            logger.info("Paused — skipping research turn (BR-3.1)")
            return
        logger.info("Agent research turn")
        self._scheduled_turn(self.orchestrator.run_morning_research)

    def _open_execute(self) -> None:
        """At the open: place the decisions researched pre-market."""
        logger.info("Agent open execution")
        if self.steering is not None:
            self.steering.drain_offhours()  # enqueue overnight human trades (BR-2.7)
        if self._paused():
            self._funnel(self.executor.run_risk_exits)  # protection still runs (BR-3.1)
            return
        self._funnel(self._exec_pending_and_exits)

    def _intraday(self) -> None:
        """Light intraday turn + execution — only while the session is open."""
        if not self.executor.broker.is_market_open():
            return
        if self._paused():
            self._funnel(self.executor.run_risk_exits)  # protection still runs (BR-3.1)
            return
        logger.info("Agent intraday cycle")
        # F3: inject the Python-assembled brief (steering on); else legacy prompt.
        brief = self._brief(include_news=True) if self.steering is not None else None
        self._scheduled_turn(lambda: self.orchestrator.run_intraday(brief))
        self._funnel(self._exec_pending_and_exits)

    def _eod(self) -> None:
        logger.info("Agent end-of-day cycle")
        from src.agent.equity_log import fetch_benchmark, record_equity
        from src.agent.review import outcome_lines

        if not self._paused():
            decisions = self.executor.journal.read_decisions()
            outcomes = outcome_lines(decisions, self.executor.broker, self.executor.data_provider)
            self._scheduled_turn(lambda: self.orchestrator.run_eod_review(outcomes=outcomes))
            self._funnel(self.executor.execute_pending)

        # Daily marks for the track record. record_trade_ledger() is a no-op on
        # brokers that don't reconstruct closed round-trips (e.g. simulated);
        # AlpacaBroker overrides it -- callers stay broker-agnostic.
        root = self.executor.journal.root
        record_equity(
            self.executor.broker.get_portfolio_state(),
            root / "equity.jsonl",
            benchmark=fetch_benchmark(self.executor.data_provider),
        )
        self.executor.broker.record_trade_ledger(
            root / "trades.jsonl",
            since=self.experiment_start,
            min_notional=self.min_trade_notional,
        )

    # ------------------------------------------------------------------ #
    def _launch(self, fresh: bool = False) -> None:
        """Initial turns on launch.

        Research runs only if today's session doesn't exist yet (first launch of
        the trading day) — a same-day restart **resumes** the existing session and
        skips the (expensive) research turn, staying connected to the research it
        already did. ``fresh`` forces a clean session. Pending decisions and
        protection are always reconciled (cheap; gated to RTH internally).
        """
        if fresh:
            self.orchestrator.session.reset_session()
        # A launch-turn failure (e.g. a research timeout) must NOT kill the
        # daemon — log it and let the scheduler take over (next cron retries).
        try:
            if self.orchestrator.session.is_started():
                logger.info("Resuming today's session — skipping the launch research turn")
            else:
                self._premarket_research()
            self._open_execute()
        except Exception as e:
            logger.error("Launch turn failed ({}); scheduler continues, next cron will retry", e)

    def start(self, fresh: bool = False) -> None:
        logger.info(
            f"Starting agent trading mode (research {self.research_hour:02d}:"
            f"{self.research_minute:02d} ET, intraday every {self.intraday_minutes} min)"
        )
        if self.steering is not None:
            self.steering.start()  # bus + hook settings + token (before any turn spawns the agent)

        self.scheduler.add_daily_job(
            self._premarket_research, hour=self.research_hour,
            minute=self.research_minute, job_id="agent_research",
        )
        self.scheduler.add_market_open_job(self._open_execute, job_id="agent_open")
        self.scheduler.add_batch_job(
            self._intraday, interval_minutes=self.intraday_minutes, job_id="agent_intraday"
        )
        self.scheduler.add_market_close_job(self._eod, job_id="agent_eod")
        if self.steering is not None:
            self.scheduler.add_seconds_job(self.steering.poll_commands, 2, "steering_poll")
            self.scheduler.add_seconds_job(self.steering.publish_snapshot, 5, "steering_snapshot")
            self.scheduler.add_seconds_job(self.steering.poll_agent_questions, 5, "steering_questions")
            self.scheduler.add_daily_job(
                self.steering.daily_sweep, hour=0, minute=1, job_id="steering_sweep"
            )
            # F6: today's round-trip summary (one broker get_fills call, slow cadence —
            # folded into the snapshot by publish_snapshot) + the deep-monitoring view.
            self.scheduler.add_seconds_job(
                lambda: self.steering.refresh_round_trip(since=self.experiment_start),
                45, "steering_roundtrip")
            self.scheduler.add_seconds_job(self.steering.publish_monitor, 10, "steering_monitor")
            # F8: sidebar enrichment — current price of resting-order symbols we
            # don't hold (held symbols reuse position.current_price) + the recent-
            # fills list; both cached on the worker and folded into the snapshot.
            self.scheduler.add_seconds_job(
                self.steering.refresh_order_prices, 12, "steering_order_prices")
            self.scheduler.add_seconds_job(
                self.steering.refresh_recent_fills, 45, "steering_recent_fills")
            # F3: event-driven wake detector (reads cached snapshot/bars only) + the
            # daily watch fired-set sweep + the background news poller.
            self.scheduler.add_seconds_job(
                self._wake.detect_wakes, self.intraday_config.wake_detect_seconds, "agent_wake")
            self.scheduler.add_daily_job(
                self._watch.sweep, hour=0, minute=1, job_id="agent_watch_sweep")
            self._news.start()
        self.scheduler.start()

        # Launch turns (premarket research can take MINUTES) run AFTER the scheduler is
        # live, so steering (poll_commands/publish_snapshot every 2-5s) is responsive from
        # t=0 instead of being dead until the startup research finishes. The turn_lock +
        # CommandBus serialize this launch turn against any scheduled turn, so it is
        # race-safe to have the scheduler already running here.
        self._launch(fresh=fresh)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Agent trading stopped by user")
            self.stop()

    def stop(self) -> None:
        self.scheduler.stop()
        if self._news is not None:
            self._news.stop()
        if self.steering is not None:
            self.steering.stop()

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
        # F82: intraday feature auto-collection state (wired in start()).
        self._intraday_collect_enabled = False
        self._intraday_store = None
        self._intraday_tf = None
        self._intraday_backfill_thread = None
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
            self.orchestrator._on_turn_start = self.steering.set_current_turn
            self.orchestrator._on_turn_end = self.steering.clear_current_turn

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
        self._bar_cache = bar_cache  # F14: kept so the agent_prefetch job can warm it
        self._watch = WatchStore(root)
        self._brief_assembler = BriefAssembler(
            bar_cache, state=self.steering.state, watch_store=self._watch,
            sentiment_lines_fn=self._sentiment_lines_fn())
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

    # ------------------------------------------------------------------ #
    # F77: retail sentiment (StockTwits) — hourly sweep + brief lines
    # ------------------------------------------------------------------ #
    def _sentiment_config(self):
        from config.config import get_settings
        from src.signals.settings import SignalsConfig
        return SignalsConfig.from_settings(get_settings().signals).sentiment

    def _holdings_config(self):
        from config.config import get_settings
        from src.signals.settings import SignalsConfig
        return SignalsConfig.from_settings(get_settings().signals).disclosed_holdings

    def _setup_holdings_refresh(self) -> None:
        """Register the periodic disclosed-holdings (13F) refresh (F81, FR-2/FR-7).

        Best-effort wiring: any failure here disables the refresh but never the
        daemon (NFR-1). The tick itself absorbs all runtime errors. Runs once on
        boot (next_run_time now) then every ``refresh_hours`` — 13F is quarterly,
        so the cadence only needs to catch a new filing, not poll hot."""
        try:
            import threading

            from config.config import get_settings

            cfg = self._holdings_config()
            if not cfg.enabled:
                return
            from src.signals.holdings.provider import build_providers
            from src.signals.holdings.refresher import HoldingsRefresher

            providers = build_providers(cfg.providers, get_settings())
            if not providers:
                logger.info("holdings refresh: no usable providers — skipping")
                return
            refresher = HoldingsRefresher(
                providers=providers, root=self.executor.journal.root)
            self.scheduler.add_seconds_job(
                refresher.refresh_tick, int(cfg.refresh_hours * 3600),
                "holdings_refresh", misfire_grace_time=3600)
            # Prime the cache on boot (interval trigger only fires after the first
            # period) on a daemon thread so a slow SEC fetch never stalls startup.
            # refresh_tick absorbs all errors, so the thread is fire-and-forget.
            threading.Thread(
                target=refresher.refresh_tick, name="holdings-refresh-prime",
                daemon=True).start()
            logger.info("holdings refresh scheduled every {}h ({} provider(s))",
                        cfg.refresh_hours, len(providers))
        except Exception as exc:
            logger.warning("holdings refresh not scheduled: {}", exc)

    def _sentiment_lines_fn(self):
        """(symbols) -> intraday brief lines for sentiment outliers, or None."""
        try:
            cfg = self._sentiment_config()
            if not cfg.enabled:
                return None
            root = self.executor.journal.root

            def lines(symbols: list[str]) -> list[str]:
                from src.signals.sentiment import outlier_lines_for
                return outlier_lines_for(symbols, cfg, root=root)

            return lines
        except Exception as exc:  # optional context — never block intraday setup
            logger.warning("sentiment brief lines disabled: {}", exc)
            return None

    def _setup_sentiment_sweep(self) -> None:
        """Register the hourly StockTwits sweep (plain HTTP, no LLM cost).

        Best-effort wiring: any failure here disables the sweep but never the
        daemon (NFR-1). The tick itself absorbs all runtime errors."""
        try:
            cfg = self._sentiment_config()
            if not cfg.enabled:
                return
            from src.signals.sentiment_sweep import SentimentSweeper
            from src.signals.sources.stocktwits import StocktwitsSource

            sweeper = SentimentSweeper(
                source=StocktwitsSource(),
                universe=list(self.executor.universe),
                cfg=cfg,
                root=self.executor.journal.root,
            )
            self.scheduler.add_seconds_job(
                sweeper.sweep_tick, cfg.sweep_minutes * 60, "sentiment_sweep",
                misfire_grace_time=600)
            logger.info("sentiment sweep scheduled every {}m (ET window {}-{})",
                        cfg.sweep_minutes, cfg.window_et[0], cfg.window_et[1])
        except Exception as exc:
            logger.warning("sentiment sweep not scheduled: {}", exc)

    def _intraday_symbols(self) -> list[str]:
        from src.agent.intraday.util import held_and_watched
        snap = self.steering.last_snapshot if self.steering else None
        return held_and_watched(snap, self._watch)

    def _prefetch_intraday(self) -> None:
        """F14: warm the BarCache for held+watched symbols on its OWN scheduler
        job, so the 5s WakeDetector tick only ever READS the cache (peek_*) and
        never blocks on a market-data fetch. Best-effort; the underlying get_* are
        HTTP-timeout-bounded (F14-A) so a slow symbol can't wedge this thread."""
        try:
            self._bar_cache.prefetch(self._intraday_symbols())
        except Exception as e:  # never kill the scheduler (NFR-4)
            logger.error("intraday prefetch failed (continuing): {}", e)

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

    def _exec_pending_and_exits(self):
        outcomes = self.executor.execute_pending()
        self.executor.run_risk_exits()
        return outcomes

    def _emit_exec_outcomes(self, outcomes, context: str = "") -> None:
        """Surface non-executed outcomes to the steering channel so the operator
        and agent are aware of failures that would otherwise be silent."""
        if self.steering is None or not outcomes:
            return
        for o in outcomes:
            if o.status in ("no_order", "error"):
                logger.warning(
                    "{}: {} {} -> {} ({})",
                    context, o.decision.symbol, o.decision.action,
                    o.status, o.detail,
                )
                try:
                    from src.agent.steering.records import SteeringEvent
                    self.steering.channel.append_event(
                        SteeringEvent(
                            kind="exec_outcome",
                            payload={
                                "symbol": o.decision.symbol,
                                "action": o.decision.action,
                                "status": o.status,
                                "detail": o.detail,
                                "ts": o.decision.ts.isoformat(),
                            },
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to emit exec outcome event: {e}")

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
        outcomes = self._funnel(self._exec_pending_and_exits)
        self._emit_exec_outcomes(outcomes, context="open_execute")

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
        outcomes = self._funnel(self._exec_pending_and_exits)
        self._emit_exec_outcomes(outcomes, context="intraday")

    def _save_quality_report(self) -> None:
        """EOD: persist decision quality report to workspace/quality/<date>.json.
        JSON only; no prompt injection (LLM shouldn't see small-sample metrics).
        Fetches fills from the broker for round-trip matching (MAE/MFE/R:R)."""
        try:
            from src.agent.quality.collector import collect_outcomes
            from src.agent.quality.aggregate import summary

            logger.info("Saving decision quality report")
            fills = []
            try:
                fills = self.executor.broker.get_fills()
            except Exception:
                pass
            outcomes = collect_outcomes(self.executor.journal, fills=fills)
            if not outcomes:
                logger.info("No decision outcomes to report")
                return
            s = summary(outcomes)
            import json
            from datetime import date

            out_dir = self.executor.journal.root / "quality"
            out_dir.mkdir(exist_ok=True)
            out_file = out_dir / f"{date.today().isoformat()}.json"
            out_file.write_text(json.dumps(s, indent=2, default=str), encoding="utf-8")
            logger.info(f"Quality report saved to {out_file}")
        except Exception as exc:
            logger.warning(f"Quality report failed (non-fatal): {exc}")

    def _run_surge_scan(self) -> int:
        """EOD surge/dive scan — runs before the EOD review so the agent can
        analyse the results.  Returns the number of surge records written."""
        try:
            from src.surge.detector import SurgeDetector
            from src.surge.settings import SurgeDetectionConfig
            from src.surge.store import SurgeStore
            from config.config import CONFIG_DIR, load_yaml_config

            # Read yaml directly: Settings(extra="ignore") drops the ``surge`` block.
            config = SurgeDetectionConfig.from_settings(
                load_yaml_config(CONFIG_DIR / "settings.yaml")
            )
            detector = SurgeDetector(self.executor.data_provider, config)
            records = detector.scan(list(self.executor.universe))
            store = SurgeStore(base_dir=self.executor.journal.root / "surge")
            written = store.write_records(records)
            if written > 0:
                logger.info(f"surge scan: {written} new record(s) written")
            return written
        except Exception:
            logger.exception("surge scan failed (non-fatal)")
            return 0

    def _setup_intraday_collection(self) -> None:
        """F82: auto-collect intraday session features for the universe.

        On start, gap-backfill each symbol's history in a daemon thread (so a
        multi-year × ~100-symbol backfill never blocks startup); the EOD job then
        appends each day's session (see ``_eod``). Best-effort — any failure here
        disables collection but never the daemon."""
        try:
            from config.config import CONFIG_DIR, get_settings, load_yaml_config
            from src.core.types import TimeFrame
            from src.data.intraday.auto import CollectionConfig
            from src.data.intraday.store import IntradayFeatureStore

            # Read yaml directly: Settings(extra="ignore") drops the block.
            cfg = CollectionConfig.from_yaml(load_yaml_config(CONFIG_DIR / "settings.yaml"))
            if not cfg.enabled:
                logger.info("intraday auto-collection disabled (config) — not scheduled")
                return

            timeframe = TimeFrame(cfg.timeframe)
            self._intraday_collect_enabled = True
            self._intraday_store = IntradayFeatureStore()
            self._intraday_tf = timeframe

            # Backfill needs deep history → alpaca range fetch; else reuse the
            # daemon's provider (EOD append always uses it — recent bars suffice).
            if cfg.provider == "alpaca":
                from src.data.intraday.collector import _provider
                backfill_provider = _provider("alpaca", get_settings())
            else:
                backfill_provider = self.executor.data_provider

            import threading
            from src.core.markettime import et_today
            from src.data.intraday.auto import backfill_universe

            store = self._intraday_store

            def _run_backfill() -> None:
                try:
                    backfill_universe(
                        backfill_provider, store, sorted(self.executor.universe),
                        today=et_today(), backfill_years=cfg.backfill_years,
                        timeframe=timeframe,
                    )
                except Exception:
                    logger.exception("intraday backfill failed (non-fatal)")

            t = threading.Thread(
                target=_run_backfill, name="intraday-backfill", daemon=True
            )
            self._intraday_backfill_thread = t
            t.start()
            logger.info(
                "intraday auto-collection enabled (provider={}, backfill {}y, tf={})",
                cfg.provider, cfg.backfill_years, cfg.timeframe,
            )
        except Exception:
            logger.exception("intraday auto-collection wiring failed (non-fatal)")

    def _setup_early_session(self) -> None:
        """F51/F56: wire the early-session monitor into the scheduler.

        A market-open job calls ``start()`` (begins the polling window) and a
        seconds-job drives ``tick()`` (a no-op until ``start()`` runs and again
        after the ET ``monitor_end``). Disabled cleanly when the config switch is
        off. Best-effort — a wiring failure must never abort daemon startup."""
        try:
            from config.config import CONFIG_DIR, load_yaml_config
            from src.early_session.settings import EarlySessionConfig
            from src.early_session.monitor import EarlySessionMonitor

            # Read the yaml directly: Settings(extra="ignore") drops the
            # ``early_session`` block, so get_settings() can't carry it.
            config = EarlySessionConfig.from_settings(
                load_yaml_config(CONFIG_DIR / "settings.yaml")
            )
            if not config.enabled:
                logger.info("Early-session monitor disabled (config) — not scheduled")
                return

            monitor = EarlySessionMonitor(
                config=config,
                data_provider=self.executor.data_provider,
                workspace_root=self.executor.journal.root,
                symbols=lambda: list(self.executor.universe),
            )
            self._early_session = monitor  # keep a ref so the jobs aren't GC'd
            self.scheduler.add_market_open_job(
                monitor.start, job_id="early_session_start"
            )
            self.scheduler.add_seconds_job(
                monitor.tick, config.poll_interval_seconds, "early_session_tick"
            )
            logger.info("Early-session monitor scheduled (poll {}s)", config.poll_interval_seconds)
        except Exception:
            logger.exception("early-session wiring failed (non-fatal)")

    def _eod(self) -> None:
        logger.info("Agent end-of-day cycle")
        from src.agent.logs.equity import fetch_benchmark, record_equity
        from src.agent.learning.review import outcome_lines

        # F47: scan for surge/dive stocks before the EOD review so the agent
        # can run ``surge-list`` / ``surge-analyze`` during the review turn.
        surge_count = self._run_surge_scan()

        # F82: append today's intraday session features for the universe.
        # Best-effort — never block the EOD trading cycle on a data-collection error.
        if self._intraday_collect_enabled:
            try:
                from src.core.markettime import et_today
                from src.data.intraday.auto import collect_today
                collect_today(
                    self.executor.data_provider, self._intraday_store,
                    sorted(self.executor.universe), today=et_today(),
                    timeframe=self._intraday_tf,
                )
            except Exception:
                logger.exception("intraday EOD collect failed (non-fatal)")

        if not self._paused():
            decisions = self.executor.journal.read_decisions()
            outcomes = outcome_lines(decisions, self.executor.broker, self.executor.data_provider)
            self._scheduled_turn(
                lambda: self.orchestrator.run_eod_review(
                    outcomes=outcomes, surge_count=surge_count,
                )
            )
            outcomes = self._funnel(self.executor.execute_pending)
            self._emit_exec_outcomes(outcomes, context="eod")
            self._save_quality_report()

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

    def _resolve_research_schedule(self) -> tuple[int, int]:
        """Compute research start hour:minute from start_before_open config."""
        from config.config import get_settings
        cfg = get_settings().agent
        market_open_min = 9 * 60 + 30
        start_min = market_open_min - cfg.research_start_before_open
        return start_min // 60, start_min % 60

    def _resolve_research_timeout(self) -> float:
        from config.config import get_settings
        cfg = get_settings().agent
        auto = (cfg.research_start_before_open - cfg.research_end_before_open) * 60.0
        if abs(cfg.research_timeout - 1800.0) > 0.001:
            logger.warning("research_timeout={:.0f}s overrides auto={:.0f}s", cfg.research_timeout, auto)
            return cfg.research_timeout
        return auto

    def _oco_reconcile_tick(self) -> None:
        """Cancel the dangling OCO leg after a position exits (KIS emulated OCO).
        Always-on so a standalone (no-steering) KIS run still reconciles."""
        try:
            self.executor.broker.reconcile_oco()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"OCO reconcile tick skipped: {e}")

    def start(self, fresh: bool = False) -> None:
        rh, rm = self._resolve_research_schedule()
        resolved_timeout = self._resolve_research_timeout()
        self.orchestrator.research_timeout = resolved_timeout
        logger.info(
            f"Starting agent trading mode (research {rh:02d}:{rm:02d} ET, "
            f"timeout {resolved_timeout:.0f}s, intraday every {self.intraday_minutes} min)"
        )
        if self.steering is not None:
            self.steering.start()

        # Broker-driven trading calendar: a KR broker (KIS) carries a KST schedule;
        # others fall back to the US/Eastern defaults.
        broker = self.executor.broker
        sched = getattr(broker, "market_schedule", None)
        if sched:
            tz = sched["timezone"]
            self.scheduler.add_daily_job(
                self._premarket_research, hour=sched["research"][0],
                minute=sched["research"][1], job_id="agent_research", timezone=tz,
            )
            self.scheduler.add_market_open_job(
                self._open_execute, "agent_open", timezone=tz,
                hour=sched["open"][0], minute=sched["open"][1])
            self.scheduler.add_market_close_job(
                self._eod, "agent_eod", timezone=tz,
                hour=sched["close"][0], minute=sched["close"][1])
        else:
            self.scheduler.add_daily_job(
                self._premarket_research, hour=rh, minute=rm, job_id="agent_research",
            )
            self.scheduler.add_market_open_job(self._open_execute, job_id="agent_open")
            self.scheduler.add_market_close_job(self._eod, job_id="agent_eod")
        self.scheduler.add_batch_job(
            self._intraday, interval_minutes=self.intraday_minutes, job_id="agent_intraday"
        )
        self._setup_early_session()
        # F77: hourly retail-sentiment sweep (steering-independent, plain HTTP).
        self._setup_sentiment_sweep()
        # F81: periodic disclosed-holdings (13F) refresh — the only HTTP path; the
        # turn/universe read the cache it writes.
        self._setup_holdings_refresh()
        # F82: intraday feature auto-collection (gap-backfill thread + EOD append).
        self._setup_intraday_collection()
        # Always-on (steering-independent) OCO reconcile for brokers that emulate
        # OCO at the exchange (KIS): cancels the dangling leg once a position exits.
        # The steering seconds-jobs below are gated on steering, so a standalone KIS
        # run would otherwise never reconcile (F30 HIGH-1).
        if hasattr(broker, "reconcile_oco"):
            self.scheduler.add_seconds_job(self._oco_reconcile_tick, 5, "kis_reconcile")
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
            # F69: lightweight system-health publish for the TUI (steering/health.json).
            # Runs cheap, no-external-call dimensions on a pool worker; 0 disables it.
            from config.config import get_settings
            _health_secs = get_settings().monitoring.health_publish_seconds
            if _health_secs > 0:
                self.scheduler.add_seconds_job(
                    self.steering.publish_health, _health_secs, "steering_health")
            # F8: sidebar enrichment — current price of resting-order symbols we
            # don't hold (held symbols reuse position.current_price) + the recent-
            # fills list; both cached on the worker and folded into the snapshot.
            self.scheduler.add_seconds_job(
                self.steering.refresh_order_prices, 12, "steering_order_prices")
            self.scheduler.add_seconds_job(
                self.steering.refresh_recent_fills, 45, "steering_recent_fills")
            # F3: event-driven wake detector (reads cached snapshot/bars only) + the
            # daily watch fired-set sweep + the background news poller.
            # F14: warm the bar/price cache off the detect thread so detect_wakes
            # only reads (peek_*) — registered BEFORE agent_wake so the cache fills
            # first. price every tick, bars gated by bars_ttl inside prefetch.
            self.scheduler.add_seconds_job(
                self._prefetch_intraday, self.intraday_config.prefetch_seconds, "agent_prefetch")
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

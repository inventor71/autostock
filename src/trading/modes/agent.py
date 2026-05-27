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
    ):
        self.orchestrator = orchestrator
        self.executor = executor
        self.intraday_minutes = intraday_minutes
        self.research_hour = research_hour
        self.research_minute = research_minute
        self.scheduler = TradingScheduler()

    # ------------------------------------------------------------------ #
    # Cycles
    # ------------------------------------------------------------------ #
    def _premarket_research(self) -> None:
        """Deep research turn — may run pre-market; writes decisions only."""
        logger.info("Agent research turn")
        self.orchestrator.run_morning_research()

    def _open_execute(self) -> None:
        """At the open: place the decisions researched pre-market."""
        logger.info("Agent open execution")
        self.executor.execute_pending()
        self.executor.run_risk_exits()

    def _intraday(self) -> None:
        """Light intraday turn + execution — only while the session is open."""
        if not self.executor.broker.is_market_open():
            return
        logger.info("Agent intraday cycle")
        self.orchestrator.run_intraday()
        self.executor.execute_pending()
        self.executor.run_risk_exits()

    def _eod(self) -> None:
        logger.info("Agent end-of-day cycle")
        from src.agent.review import outcome_lines

        decisions = self.executor.journal.read_decisions()
        outcomes = outcome_lines(decisions, self.executor.broker, self.executor.data_provider)
        self.orchestrator.run_eod_review(outcomes=outcomes)
        self.executor.execute_pending()

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        logger.info(
            f"Starting agent trading mode (research {self.research_hour:02d}:"
            f"{self.research_minute:02d} ET, intraday every {self.intraday_minutes} min)"
        )
        # Research now so a manual launch is productive immediately; if the
        # market is already open, place the decisions too.
        self._premarket_research()
        if self.executor.broker.is_market_open():
            self._open_execute()

        self.scheduler.add_daily_job(
            self._premarket_research, hour=self.research_hour,
            minute=self.research_minute, job_id="agent_research",
        )
        self.scheduler.add_market_open_job(self._open_execute, job_id="agent_open")
        self.scheduler.add_batch_job(
            self._intraday, interval_minutes=self.intraday_minutes, job_id="agent_intraday"
        )
        self.scheduler.add_market_close_job(self._eod, job_id="agent_eod")
        self.scheduler.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Agent trading stopped by user")
            self.stop()

    def stop(self) -> None:
        self.scheduler.stop()

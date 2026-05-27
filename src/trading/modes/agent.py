"""Agent trading mode: the full PM loop (brain + body) on a schedule.

Composes the slow-loop orchestrator (the LLM PM agent writing the journal) with
the decision executor (reading decisions.jsonl and trading via RiskManager ->
Broker). Each scheduled cycle runs the appropriate turn and then executes any
new decisions; intraday cycles also run the polled risk-exit backup.

Unlike BatchTradingMode this does NOT run a cycle immediately on start (a turn
spends LLM budget); it only registers the market-hours jobs.
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
        intraday_minutes: int = 30,
    ):
        self.orchestrator = orchestrator
        self.executor = executor
        self.intraday_minutes = intraday_minutes
        self.scheduler = TradingScheduler()

    def _morning(self) -> None:
        logger.info("Agent morning cycle")
        self.orchestrator.run_morning_research()
        self.executor.execute_pending()

    def _intraday(self) -> None:
        logger.info("Agent intraday cycle")
        self.orchestrator.run_intraday()
        self.executor.execute_pending()
        self.executor.run_risk_exits()

    def _eod(self) -> None:
        logger.info("Agent end-of-day cycle")
        self.orchestrator.run_eod_review()
        self.executor.execute_pending()

    def start(self) -> None:
        logger.info(
            f"Starting agent trading mode (intraday every {self.intraday_minutes} min)"
        )
        self.scheduler.add_market_open_job(self._morning, job_id="agent_morning")
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

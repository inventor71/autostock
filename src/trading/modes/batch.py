from __future__ import annotations

import time

from loguru import logger

from src.trading.engine import TradingEngine
from src.trading.scheduler import TradingScheduler


class BatchTradingMode:
    """Periodic batch trading mode.

    Runs the trading cycle at fixed intervals using APScheduler.
    """

    def __init__(
        self,
        engine: TradingEngine,
        interval_minutes: int = 60,
    ):
        self.engine = engine
        self.interval_minutes = interval_minutes
        self.scheduler = TradingScheduler()
        self._cycle_count = 0

    def _run_cycle(self) -> None:
        self._cycle_count += 1
        logger.info(f"Batch cycle #{self._cycle_count} starting...")
        try:
            orders = self.engine.run_cycle()
            logger.info(f"Cycle #{self._cycle_count} complete: {len(orders)} orders filled")
        except Exception as e:
            logger.error(f"Cycle #{self._cycle_count} failed: {e}")

    def start(self) -> None:
        """Start batch trading."""
        logger.info(
            f"Starting batch trading mode (interval={self.interval_minutes}min)"
        )

        # Run first cycle immediately
        self._run_cycle()

        # Schedule subsequent cycles
        self.scheduler.add_batch_job(
            self._run_cycle,
            interval_minutes=self.interval_minutes,
        )
        self.scheduler.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Batch trading stopped by user")
            self.stop()

    def stop(self) -> None:
        self.scheduler.stop()

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger


class TradingScheduler:
    """APScheduler-based scheduler for trading operations."""

    def __init__(self):
        self._scheduler = BackgroundScheduler()
        self._running = False

    def add_batch_job(
        self,
        func,
        interval_minutes: int = 60,
        job_id: str = "batch_trading",
    ) -> None:
        """Add a periodic batch trading job."""
        self._scheduler.add_job(
            func,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=job_id,
            replace_existing=True,
        )
        logger.info(f"Scheduled batch job '{job_id}' every {interval_minutes} min")

    def add_market_open_job(self, func, job_id: str = "market_open") -> None:
        """Run a job at US market open (9:30 AM ET, Mon-Fri)."""
        self._scheduler.add_job(
            func,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=9,
                minute=30,
                timezone="US/Eastern",
            ),
            id=job_id,
            replace_existing=True,
        )
        logger.info(f"Scheduled market open job '{job_id}'")

    def add_market_close_job(self, func, job_id: str = "market_close") -> None:
        """Run a job near US market close (3:55 PM ET, Mon-Fri)."""
        self._scheduler.add_job(
            func,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=15,
                minute=55,
                timezone="US/Eastern",
            ),
            id=job_id,
            replace_existing=True,
        )
        logger.info(f"Scheduled market close job '{job_id}'")

    def start(self) -> None:
        if not self._running:
            self._scheduler.start()
            self._running = True
            logger.info("Scheduler started")

    def stop(self) -> None:
        if self._running:
            self._scheduler.shutdown()
            self._running = False
            logger.info("Scheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._running

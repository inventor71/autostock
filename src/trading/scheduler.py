from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

# Make the serialization assumptions explicit rather than relying on APScheduler
# defaults (critic #3): a job never self-overlaps (max_instances=1) and a missed
# fire coalesces into one (coalesce=True). The F4 turn_lock handles cross-job
# (scheduled vs reconcile) serialization; this handles a job vs itself.
# ``misfire_grace_time`` lets a job that fired late (thread-pool contention, a
# slow tick) still run within the grace window instead of being dropped outright
# (F3 critic#3: a blocked seconds-job would otherwise silently lose ticks).
_JOB_DEFAULTS = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 30}


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
            **_JOB_DEFAULTS,
        )
        logger.info(f"Scheduled batch job '{job_id}' every {interval_minutes} min")

    def add_seconds_job(self, func, seconds: float, job_id: str) -> None:
        """Add a short-cadence job (e.g. the F4 file-drop poll / snapshot publisher).
        coalesce collapses a backlog; max_instances=1 prevents self-overlap."""
        self._scheduler.add_job(
            func,
            trigger=IntervalTrigger(seconds=seconds),
            id=job_id,
            replace_existing=True,
            **_JOB_DEFAULTS,
        )
        logger.info(f"Scheduled seconds job '{job_id}' every {seconds}s")

    def add_daily_job(
        self,
        func,
        hour: int,
        minute: int = 0,
        job_id: str = "daily",
        day_of_week: str = "mon-fri",
        timezone: str = "US/Eastern",
    ) -> None:
        """Run a job daily at a given ET time (e.g. pre-market research at 09:00)."""
        self._scheduler.add_job(
            func,
            trigger=CronTrigger(
                day_of_week=day_of_week, hour=hour, minute=minute, timezone=timezone
            ),
            id=job_id,
            replace_existing=True,
            **_JOB_DEFAULTS,
        )
        logger.info(f"Scheduled daily job '{job_id}' at {hour:02d}:{minute:02d} {timezone}")

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
            **_JOB_DEFAULTS,
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
            **_JOB_DEFAULTS,
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

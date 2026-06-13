from __future__ import annotations

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

# F14: APScheduler's default ThreadPoolExecutor is 10 workers. With the F3/F6/F8
# steering seconds-jobs (poll/snapshot/questions/monitor/order_prices/roundtrip/
# recent_fills) + agent_wake + the new agent_prefetch, plus cron jobs that can fire
# concurrently, 10 leaves almost no headroom — a few blocked HTTP calls could starve
# the pool. Raise it so a slow (now HTTP-timeout-bounded) job can't starve the rest.
_MAX_WORKERS = 16

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
        self._scheduler = BackgroundScheduler(
            executors={"default": ThreadPoolExecutor(_MAX_WORKERS)}
        )
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

    def add_seconds_job(self, func, seconds: float, job_id: str,
                        misfire_grace_time: int | None = None) -> None:
        """Add a short-cadence job (e.g. the F4 file-drop poll / snapshot publisher).
        coalesce collapses a backlog; max_instances=1 prevents self-overlap.

        ``misfire_grace_time`` overrides the 30s default for long-interval jobs
        (F77 critic: an hourly job missed by a 30s-busy pool would otherwise
        silently skip to the NEXT hour — give it a grace matched to its period)."""
        defaults = dict(_JOB_DEFAULTS)
        if misfire_grace_time is not None:
            defaults["misfire_grace_time"] = misfire_grace_time
        self._scheduler.add_job(
            func,
            trigger=IntervalTrigger(seconds=seconds),
            id=job_id,
            replace_existing=True,
            **defaults,
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

    def add_market_open_job(
        self,
        func,
        job_id: str = "market_open",
        timezone: str = "US/Eastern",
        hour: int = 9,
        minute: int = 30,
    ) -> None:
        """Run a job at market open. Defaults to US open (9:30 AM ET, Mon-Fri);
        a KR broker passes timezone="Asia/Seoul", hour=9, minute=0."""
        self._scheduler.add_job(
            func,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=hour,
                minute=minute,
                timezone=timezone,
            ),
            id=job_id,
            replace_existing=True,
            **_JOB_DEFAULTS,
        )
        logger.info(f"Scheduled market open job '{job_id}' at {hour:02d}:{minute:02d} {timezone}")

    def add_market_close_job(
        self,
        func,
        job_id: str = "market_close",
        timezone: str = "US/Eastern",
        hour: int = 15,
        minute: int = 55,
    ) -> None:
        """Run a job near market close. Defaults to US close (3:55 PM ET, Mon-Fri);
        a KR broker passes timezone="Asia/Seoul", hour=15, minute=20."""
        self._scheduler.add_job(
            func,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=hour,
                minute=minute,
                timezone=timezone,
            ),
            id=job_id,
            replace_existing=True,
            **_JOB_DEFAULTS,
        )
        logger.info(f"Scheduled market close job '{job_id}' at {hour:02d}:{minute:02d} {timezone}")

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

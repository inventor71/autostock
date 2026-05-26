"""Logging configuration for autostock (loguru-based).

Every application module logs through ``from loguru import logger``. Standard
library logging emitted by third-party packages (yfinance, urllib3, apscheduler,
alpaca, ...) is intercepted and re-routed into loguru, so the whole process logs
through a single pipeline and a single set of sinks (console + rotating file).

Usage:
    from src.monitoring.logger import setup_logging
    setup_logging(level="DEBUG", log_file="logs/autostock.log")

    # anywhere else:
    from loguru import logger
    logger.info("hello")
"""

from __future__ import annotations

import inspect
import logging
import sys
from pathlib import Path

from loguru import logger

# Base log directory (relative to project root).
LOG_DIR = Path(__file__).parent.parent.parent / "logs"

# One format for both sinks. loguru strips the color markup automatically when
# the sink is not a TTY (e.g. the log file), so the file stays plain text.
LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

# Chatty third-party loggers: capped to WARNING so a DEBUG run still surfaces
# our own decision logs without drowning in library noise.
_NOISY_LOGGERS = (
    "yfinance",
    "peewee",
    "urllib3",
    "apscheduler",
    "asyncio",
    "matplotlib",
    "httpx",
    "httpcore",
    "alpaca",
)


class InterceptHandler(logging.Handler):
    """Redirect standard-library logging records into loguru.

    Installed on the root logger so anything using ``logging`` (including
    third-party libraries) flows through loguru's sinks.
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Translate the stdlib level to loguru's matching level name.
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Walk back to the frame that issued the logging call, so loguru reports
        # the real caller instead of this handler or logging's internals.
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
    console: bool = True,
) -> None:
    """Configure loguru sinks and route stdlib logging into loguru.

    Args:
        level: Logging level for our sinks (DEBUG, INFO, WARNING, ...).
        log_file: Path to the rotating log file. Defaults to ``logs/app.log``.
        console: Whether to also log to stderr.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = level.upper()

    # Replace loguru's default stderr sink with our own configured ones.
    logger.remove()

    if console:
        logger.add(
            sys.stderr,
            level=level,
            format=LOG_FORMAT,
            backtrace=False,
            diagnose=False,
        )

    if log_file is None:
        log_file = str(LOG_DIR / "app.log")
    logger.add(
        log_file,
        level=level,
        format=LOG_FORMAT,
        rotation="10 MB",
        retention=5,
        encoding="utf-8",
        enqueue=True,  # safe across threads / the realtime asyncio loop
        backtrace=False,
        diagnose=False,
    )

    # Funnel all stdlib logging through loguru, then quiet the noisy libraries.
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str | None = None):
    """Backward-compatible accessor.

    loguru records the calling module automatically, so the ``name`` argument is
    ignored and the shared loguru logger is returned.
    """
    return logger

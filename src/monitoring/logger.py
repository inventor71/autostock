"""Logging configuration for autostock.

Log directory structure:
    logs/
    ├── app.log                          # Main application log (rotating)
    ├── backtest/
    │   └── backtest_YYYYMMDD_HHMMSS.log # Individual backtest runs
    ├── trading/
    │   └── trading_YYYYMMDD.log         # Daily trading logs
    └── data/
        └── data_YYYYMMDD.log            # Data provider logs
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Literal

# Base log directory (relative to project root)
LOG_DIR = Path(__file__).parent.parent.parent / "logs"

# Sub-directories for different components
BACKTEST_LOG_DIR = LOG_DIR / "backtest"
TRADING_LOG_DIR = LOG_DIR / "trading"
DATA_LOG_DIR = LOG_DIR / "data"

# Log format
CONSOLE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _ensure_log_dirs() -> None:
    """Create log directories if they don't exist."""
    for dir_path in [LOG_DIR, BACKTEST_LOG_DIR, TRADING_LOG_DIR, DATA_LOG_DIR]:
        dir_path.mkdir(parents=True, exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance by name.

    Args:
        name: Logger name, typically __name__ from the calling module.

    Returns:
        Configured logger instance.
    """
    return logging.getLogger(name)


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
    console: bool = True,
) -> None:
    """Configure root logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Optional path to log file. If None, uses default app.log.
        console: Whether to output to console.
    """
    _ensure_log_dirs()

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT, DATE_FORMAT))
        root_logger.addHandler(console_handler)

    # File handler (rotating, 10MB max, keep 5 backups)
    if log_file is None:
        log_file = str(LOG_DIR / "app.log")

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT, DATE_FORMAT))
    root_logger.addHandler(file_handler)


def setup_backtest_logging(
    run_id: str | None = None,
    level: str = "INFO",
) -> logging.Logger:
    """Setup logging for a backtest run.

    Creates a separate log file for each backtest run to avoid
    cluttering the main log and to make analysis easier.

    Args:
        run_id: Unique identifier for this backtest run.
                If None, uses timestamp.
        level: Logging level.

    Returns:
        Logger configured for this backtest run.
    """
    _ensure_log_dirs()

    if run_id is None:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    log_file = BACKTEST_LOG_DIR / f"backtest_{run_id}.log"

    # Create backtest-specific logger
    logger = logging.getLogger(f"backtest.{run_id}")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False  # Don't propagate to root logger

    # File handler for this specific run
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT, DATE_FORMAT))
    logger.addHandler(file_handler)

    # Also add console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT, DATE_FORMAT))
    logger.addHandler(console_handler)

    logger.info(f"Backtest logging initialized: {log_file}")

    return logger


def setup_trading_logging(level: str = "INFO") -> logging.Logger:
    """Setup logging for trading operations.

    Uses daily rotating log files.

    Args:
        level: Logging level.

    Returns:
        Logger configured for trading.
    """
    _ensure_log_dirs()

    today = datetime.now().strftime("%Y%m%d")
    log_file = TRADING_LOG_DIR / f"trading_{today}.log"

    logger = logging.getLogger("trading")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    # Daily rotating file handler
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=30,  # Keep 30 days
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT, DATE_FORMAT))
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT, DATE_FORMAT))
    logger.addHandler(console_handler)

    return logger


def setup_data_logging(level: str = "INFO") -> logging.Logger:
    """Setup logging for data operations.

    Args:
        level: Logging level.

    Returns:
        Logger configured for data operations.
    """
    _ensure_log_dirs()

    today = datetime.now().strftime("%Y%m%d")
    log_file = DATA_LOG_DIR / f"data_{today}.log"

    logger = logging.getLogger("data")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=7,  # Keep 7 days
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT, DATE_FORMAT))
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT, DATE_FORMAT))
    logger.addHandler(console_handler)

    return logger


# Convenience alias for backward compatibility
logger = get_logger("autostock")

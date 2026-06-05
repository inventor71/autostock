"""Health check module for autostock system monitoring.

Provides a unified, read-only health assessment across 9 dimensions:
process, broker, data_pipeline, llm, account, risk, logs, config_env, resources.

Usage:
    from src.monitoring.health import run_all_checks, HealthReport

    report = run_all_checks(settings)  # synchronous, parallelized via threads
    print(report.model_dump_json(indent=2))
"""
from __future__ import annotations

from src.monitoring.health.checker import CheckerDispatcher
from src.monitoring.health.report import CheckResult, DimensionResult, HealthReport
from src.monitoring.health.dimensions.account import AccountChecker
from src.monitoring.health.dimensions.broker import BrokerChecker
from src.monitoring.health.dimensions.config_env import ConfigEnvChecker
from src.monitoring.health.dimensions.data_pipeline import DataPipelineChecker
from src.monitoring.health.dimensions.llm import LLMChecker
from src.monitoring.health.dimensions.logs import LogChecker
from src.monitoring.health.dimensions.process import ProcessChecker
from src.monitoring.health.dimensions.resources import ResourceChecker
from src.monitoring.health.dimensions.risk import RiskChecker

__all__ = [
    "CheckResult",
    "DimensionResult",
    "HealthReport",
    "CheckerDispatcher",
    "run_all_checks",
    # dimension checkers (for selective runs)
    "ProcessChecker",
    "BrokerChecker",
    "DataPipelineChecker",
    "LLMChecker",
    "AccountChecker",
    "RiskChecker",
    "LogChecker",
    "ConfigEnvChecker",
    "ResourceChecker",
]


from pathlib import Path


def run_all_checks(settings, project_root: Path | str | None = None) -> HealthReport:
    """Run all health checks and return a unified report.

    Args:
        settings: autostock Settings object (from config.config.get_settings()).
        project_root: Override project root directory (default: auto-detect from
            module path).  Use when running from a worktree to point at the main
            checkout's steering/ workspace/ logs/ artifacts.

    Returns:
        HealthReport with status per dimension and an overall verdict.
    """
    dispatcher = CheckerDispatcher(settings, project_root=project_root)
    dispatcher.register_all([
        ProcessChecker(settings),
        BrokerChecker(settings),
        DataPipelineChecker(settings),
        LLMChecker(settings),
        AccountChecker(settings),
        RiskChecker(settings),
        LogChecker(settings),
        ConfigEnvChecker(settings),
        ResourceChecker(settings),
    ])
    return dispatcher.run()

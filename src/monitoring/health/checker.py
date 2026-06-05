"""Checker base class and dispatcher for parallel health-check execution."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from src.monitoring.health.report import (
    CheckResult,
    CheckStatus,
    DimensionResult,
    HealthReport,
    Severity,
)

if TYPE_CHECKING:
    pass


class BaseChecker(ABC):
    """Abstract base for a dimension checker.

    Each subclass implements ``check()`` which returns a list of ``CheckResult``
    objects.  The dispatcher calls ``check()`` inside a try/except so one failing
    checker never brings down the whole report.

    ``project_root`` can be injected by the dispatcher (e.g. to point at the
    main checkout when running from a worktree).  When not set, it is derived
    from the checker module's file location.
    """

    dimension: str = "unknown"
    _project_root: Path | None = None

    @property
    def root(self) -> Path:
        """Project root directory — injected or derived from this file's location."""
        if self._project_root is not None:
            return self._project_root
        # Derive from module path: .../src/monitoring/health/dimensions/foo.py → 6 levels up
        return Path(__file__).resolve().parent.parent.parent.parent.parent

    def run_safe(self) -> DimensionResult:
        """Run ``check()`` wrapped with timing, error capture, and a per-check
        timeout guard (the checker itself manages timeouts internally)."""
        t0 = time.monotonic()
        try:
            checks = self.check()
        except Exception as exc:
            logger.warning(f"Health checker [{self.dimension}] raised: {exc}")
            checks = [
                CheckResult(
                    name=f"{self.dimension}_panic",
                    status=CheckStatus.ERROR,
                    detail=f"Checker raised {type(exc).__name__}: {exc}",
                    severity=Severity.ERROR,
                    error=str(exc),
                )
            ]
        elapsed = (time.monotonic() - t0) * 1000
        dim = DimensionResult(
            dimension=self.dimension,
            checks=checks,
        )
        dim.status = dim.worst_status
        return dim

    @abstractmethod
    def check(self) -> list[CheckResult]:
        """Return one or more check results.  Must not raise."""
        ...


class CheckerDispatcher:
    """Runs all registered checkers in parallel (ThreadPoolExecutor) and assembles
    a unified ``HealthReport``."""

    def __init__(self, settings, max_workers: int = 6, project_root: Path | str | None = None):
        self._settings = settings
        self._checkers: list[BaseChecker] = []
        self._max_workers = max_workers
        self._project_root = Path(project_root) if project_root else None

    def register(self, checker: BaseChecker) -> None:
        self._checkers.append(checker)

    def register_all(self, checkers: list[BaseChecker]) -> None:
        self._checkers.extend(checkers)

    def run(self) -> HealthReport:
        report = HealthReport()
        t0 = time.monotonic()

        if not self._checkers:
            report.overall = CheckStatus.OK
            report.summary = "No health checkers registered."
            return report

        # Inject project_root into all checkers before running
        if self._project_root is not None:
            for ch in self._checkers:
                ch._project_root = self._project_root

        futures: dict = {}
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            for ch in self._checkers:
                futures[pool.submit(ch.run_safe)] = ch.dimension

        for future in as_completed(futures):
            dim_name = futures[future]
            try:
                dim_result: DimensionResult = future.result()
            except Exception as exc:
                logger.error(f"Health dimension [{dim_name}] crashed: {exc}")
                dim_result = DimensionResult(
                    dimension=dim_name,
                    status=CheckStatus.ERROR,
                    checks=[
                        CheckResult(
                            name=f"{dim_name}_fatal",
                            status=CheckStatus.ERROR,
                            detail=f"Unhandled dispatcher error: {exc}",
                            severity=Severity.ERROR,
                            error=str(exc),
                        )
                    ],
                )
            report.dimensions[dim_name] = dim_result

        report.duration_ms = (time.monotonic() - t0) * 1000
        report.overall = self._overall(report)
        report.summary = self._build_summary(report)
        return report

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _overall(report: HealthReport) -> CheckStatus:
        """Overall report status is the worst of all dimension statuses."""
        if not report.dimensions:
            return CheckStatus.OK
        severity_order = [
            CheckStatus.OK,
            CheckStatus.SKIPPED,
            CheckStatus.WARNING,
            CheckStatus.ERROR,
            CheckStatus.CRITICAL,
        ]
        worst = CheckStatus.OK
        for dim in report.dimensions.values():
            if severity_order.index(dim.status) > severity_order.index(worst):
                worst = dim.status
        return worst

    @staticmethod
    def _build_summary(report: HealthReport) -> str:
        """Build a one-line human-readable summary."""
        parts: list[str] = []
        for dim_name in sorted(report.dimensions):
            dim = report.dimensions[dim_name]
            if dim.status == CheckStatus.OK:
                continue  # omit green dimensions for brevity
            failed = [c.name for c in dim.checks if c.status not in (CheckStatus.OK, CheckStatus.SKIPPED)]
            parts.append(f"{dim_name}({dim.status.value}): {', '.join(failed)}")
        if not parts:
            return "All checks passed."
        return " | ".join(parts)

"""Resource checks — disk space, log directory size, venv presence."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from src.monitoring.health.checker import BaseChecker
from src.monitoring.health.report import CheckResult, CheckStatus, Severity


class ResourceChecker(BaseChecker):
    dimension = "resources"

    def __init__(self, settings):
        self._settings = settings

    def check(self) -> list[CheckResult]:
        results: list[CheckResult] = []

        results.append(self._check_disk_space())
        results.append(self._check_log_size())
        results.append(self._check_venv())

        return results

    # ------------------------------------------------------------------
    # individual checks
    # ------------------------------------------------------------------

    def _check_disk_space(self) -> CheckResult:
        """Check free disk space on the project volume."""
        try:
            usage = shutil.disk_usage(str(self.root))
            free_gb = usage.free / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)
            if free_gb < 0.5:
                return CheckResult(
                    name="disk_space",
                    status=CheckStatus.WARNING,
                    detail=f"Low disk: {free_gb:.1f}GB free / {total_gb:.0f}GB",
                    severity=Severity.WARNING,
                )
            return CheckResult(
                name="disk_space",
                status=CheckStatus.OK,
                detail=f"{free_gb:.1f}GB free / {total_gb:.0f}GB",
                severity=Severity.WARNING,
            )
        except Exception as e:
            return CheckResult(
                name="disk_space",
                status=CheckStatus.WARNING,
                detail=f"Disk check failed: {e}",
                severity=Severity.WARNING,
                error=str(e),
            )

    def _check_log_size(self) -> CheckResult:
        """Check total size of logs directory."""
        logs_dir = self.root / "logs"
        if not logs_dir.exists():
            return CheckResult(
                name="log_size",
                status=CheckStatus.OK,
                detail="logs/ directory not found",
                severity=Severity.WARNING,
            )
        try:
            total = sum(
                f.stat().st_size
                for f in logs_dir.rglob("*")
                if f.is_file()
            )
            total_mb = total / (1024 * 1024)
            if total_mb > 100:
                return CheckResult(
                    name="log_size",
                    status=CheckStatus.WARNING,
                    detail=f"logs/ directory {total_mb:.0f}MB — consider cleanup",
                    severity=Severity.WARNING,
                )
            return CheckResult(
                name="log_size",
                status=CheckStatus.OK,
                detail=f"logs/ {total_mb:.1f}MB total",
                severity=Severity.WARNING,
            )
        except Exception as e:
            return CheckResult(
                name="log_size",
                status=CheckStatus.WARNING,
                detail=f"Log size check failed: {e}",
                severity=Severity.WARNING,
                error=str(e),
            )

    def _check_venv(self) -> CheckResult:
        """Check that the venv interpreter is functional."""
        venv_python = self.root / "venv" / "bin" / "python"
        if not venv_python.exists():
            return CheckResult(
                name="venv",
                status=CheckStatus.ERROR,
                detail="venv/bin/python not found",
                severity=Severity.ERROR,
            )
        # Quick import test
        try:
            import subprocess
            r = subprocess.run(
                [str(venv_python), "-c", "import loguru, pydantic, yaml"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                return CheckResult(
                    name="venv",
                    status=CheckStatus.OK,
                    detail="venv OK — core deps importable",
                    severity=Severity.ERROR,
                )
            return CheckResult(
                name="venv",
                status=CheckStatus.ERROR,
                detail=f"venv import test failed: {r.stderr[:120]}",
                severity=Severity.ERROR,
            )
        except Exception as e:
            return CheckResult(
                name="venv",
                status=CheckStatus.ERROR,
                detail=f"venv check failed: {e}",
                severity=Severity.ERROR,
                error=str(e),
            )

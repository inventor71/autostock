"""Log anomaly detection — recent ERROR/CRITICAL entries, tracebacks, rotation."""
from __future__ import annotations

import os
import time
from pathlib import Path

from src.monitoring.health.checker import BaseChecker
from src.monitoring.health.report import CheckResult, CheckStatus, Severity


class LogChecker(BaseChecker):
    dimension = "logs"

    # How far back to scan for errors (seconds)
    LOOKBACK_SECONDS = 900  # 15 minutes

    def __init__(self, settings):
        self._settings = settings

    @property
    def _log_path(self) -> Path:
        """Resolved lazily so --root injection works from the dispatcher."""
        return self.root / "logs" / "autostock.log"

    def check(self) -> list[CheckResult]:
        results: list[CheckResult] = []

        results.append(self._check_recent_errors())
        results.append(self._check_tracebacks())
        results.append(self._check_rotation())

        return results

    # ------------------------------------------------------------------
    # individual checks
    # ------------------------------------------------------------------

    def _check_recent_errors(self) -> CheckResult:
        """Count ERROR | CRITICAL log lines in the last LOOKBACK_SECONDS."""
        if not self._log_path.exists():
            return CheckResult(
                name="recent_errors",
                status=CheckStatus.OK,
                detail="autostock.log not found",
                severity=Severity.WARNING,
            )
        try:
            cutoff = time.time() - self.LOOKBACK_SECONDS
            error_count = 0
            warn_count = 0
            sample: list[str] = []

            # Read backwards in chunks to get recent lines efficiently
            with open(self._log_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                # Read last 256KB at most
                chunk_start = max(0, size - 256 * 1024)
                f.seek(chunk_start)
                raw = f.read().decode("utf-8", errors="replace")
                # Skip partial first line from the chunk
                lines = raw.splitlines()
                if chunk_start > 0 and lines:
                    lines = lines[1:]  # discard potentially partial first line

            for line in lines:
                # loguru format starts with "YYYY-MM-DD HH:MM:SS.SSS | LEVEL | ..."
                parts = line.split("|")
                if len(parts) < 2:
                    continue
                # Try to extract timestamp and level
                ts_str = parts[0].strip()
                level_str = parts[1].strip()
                # Parse timestamp
                ts = _parse_log_ts(ts_str)
                if ts is None or ts < cutoff:
                    continue
                level_upper = level_str.upper()
                if level_upper in ("ERROR", "CRITICAL"):
                    error_count += 1
                    if len(sample) < 3:
                        # Grab message part (after logger location: name:func:line -)
                        msg = parts[-1].strip() if len(parts) > 3 else line.strip()
                        sample.append(msg[:120])
                elif level_upper == "WARNING":
                    warn_count += 1

            if error_count >= 10:
                return CheckResult(
                    name="recent_errors",
                    status=CheckStatus.ERROR,
                    detail=f"{error_count} ERROR/CRITICAL in last 15min (+{warn_count} WARNING). Samples: {'; '.join(sample)}",
                    severity=Severity.WARNING,
                )
            elif error_count >= 5:
                return CheckResult(
                    name="recent_errors",
                    status=CheckStatus.WARNING,
                    detail=f"{error_count} ERROR/CRITICAL in last 15min (+{warn_count} WARNING). Samples: {'; '.join(sample)}",
                    severity=Severity.WARNING,
                )
            elif error_count > 0:
                return CheckResult(
                    name="recent_errors",
                    status=CheckStatus.WARNING,
                    detail=f"{error_count} ERROR/CRITICAL in last 15min (+{warn_count} WARNING)",
                    severity=Severity.WARNING,
                )
            return CheckResult(
                name="recent_errors",
                status=CheckStatus.OK,
                detail=f"No errors in last 15min ({warn_count} warnings)",
                severity=Severity.WARNING,
            )
        except Exception as e:
            return CheckResult(
                name="recent_errors",
                status=CheckStatus.WARNING,
                detail=f"Log scan failed: {e}",
                severity=Severity.WARNING,
                error=str(e),
            )

    def _check_tracebacks(self) -> CheckResult:
        """Detect Python tracebacks in the recent log tail."""
        if not self._log_path.exists():
            return CheckResult(
                name="tracebacks",
                status=CheckStatus.OK,
                detail="autostock.log not found",
                severity=Severity.ERROR,
            )
        try:
            cutoff = time.time() - self.LOOKBACK_SECONDS
            with open(self._log_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                chunk_start = max(0, size - 256 * 1024)
                f.seek(chunk_start)
                raw = f.read().decode("utf-8", errors="replace")
                lines = raw.splitlines()
                if chunk_start > 0 and lines:
                    lines = lines[1:]

            # Look for "Traceback (most recent call last):" in recent window
            in_traceback = False
            tb_count = 0
            for line in lines:
                parts = line.split("|")
                if len(parts) < 2:
                    if in_traceback:
                        # continuation of a traceback (no timestamp in loguru format)
                        continue
                    continue
                ts_str = parts[0].strip()
                ts = _parse_log_ts(ts_str)
                if ts is not None and ts < cutoff:
                    continue
                msg = "|".join(parts[3:]) if len(parts) > 3 else line
                if "Traceback (most recent call last)" in msg:
                    tb_count += 1
                    in_traceback = True
                else:
                    in_traceback = False

            if tb_count > 0:
                return CheckResult(
                    name="tracebacks",
                    status=CheckStatus.ERROR,
                    detail=f"{tb_count} traceback(s) in last 15min",
                    severity=Severity.ERROR,
                )
            return CheckResult(
                name="tracebacks",
                status=CheckStatus.OK,
                detail="No tracebacks in recent logs",
                severity=Severity.ERROR,
            )
        except Exception as e:
            return CheckResult(
                name="tracebacks",
                status=CheckStatus.ERROR,
                detail=f"Traceback scan failed: {e}",
                severity=Severity.ERROR,
                error=str(e),
            )

    def _check_rotation(self) -> CheckResult:
        """Check log file size — warn if >15MB without rotation."""
        if not self._log_path.exists():
            return CheckResult(
                name="log_rotation",
                status=CheckStatus.OK,
                detail="autostock.log not found",
                severity=Severity.WARNING,
            )
        try:
            size_mb = self._log_path.stat().st_size / (1024 * 1024)
            logs_dir = self.root / "logs"
            rotated = list(logs_dir.glob("autostock.log.*"))
            if size_mb > 15 and not rotated:
                return CheckResult(
                    name="log_rotation",
                    status=CheckStatus.WARNING,
                    detail=f"Log {size_mb:.1f}MB — no rotated files found (rotation may be broken)",
                    severity=Severity.WARNING,
                )
            return CheckResult(
                name="log_rotation",
                status=CheckStatus.OK,
                detail=f"Log {size_mb:.1f}MB, {len(rotated)} rotated files",
                severity=Severity.WARNING,
            )
        except Exception as e:
            return CheckResult(
                name="log_rotation",
                status=CheckStatus.WARNING,
                detail=f"Rotation check failed: {e}",
                severity=Severity.WARNING,
                error=str(e),
            )


def _parse_log_ts(ts_str: str) -> float | None:
    """Parse loguru timestamp string (YYYY-MM-DD HH:MM:SS.SSS) to epoch."""
    import re
    from datetime import datetime
    try:
        # loguru uses local time, not UTC
        dt = datetime.strptime(ts_str[:23], "%Y-%m-%d %H:%M:%S.%f")
        return dt.timestamp()
    except (ValueError, IndexError):
        pass
    # Try with just seconds
    try:
        dt = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
        return dt.timestamp()
    except (ValueError, IndexError):
        pass
    return None

"""Process liveness checks — systemd, steering snapshot, run_state."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from src.monitoring.health.checker import BaseChecker
from src.monitoring.health.report import CheckResult, CheckStatus, Severity


class ProcessChecker(BaseChecker):
    dimension = "process"

    def __init__(self, settings):
        self._settings = settings

    def check(self) -> list[CheckResult]:
        results: list[CheckResult] = []

        # 1. systemd unit active
        results.append(self._check_systemd())

        # 2. snapshot freshness
        results.append(self._check_snapshot_freshness())

        # 3. monitor freshness
        results.append(self._check_monitor_freshness())

        # 4. run_state paused / halted
        results.append(self._check_run_state())

        # 5. code version skew
        results.append(self._check_code_version())

        return results

    # ------------------------------------------------------------------
    # individual checks
    # ------------------------------------------------------------------

    def _check_systemd(self) -> CheckResult:
        """systemctl --user is-active for any autostock unit."""
        try:
            # Find any autostock* user unit
            r = subprocess.run(
                ["systemctl", "--user", "list-units", "--no-legend",
                 "--all", "autostock*"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode != 0 or not r.stdout.strip():
                # No systemd unit found — daemon might be run manually.
                # Not necessarily an error: many dev runs skip systemd.
                return CheckResult(
                    name="systemd_unit",
                    status=CheckStatus.OK,
                    detail="No autostock systemd unit (manual run assumed)",
                    severity=Severity.CRITICAL,
                )

            # Parse: UNIT  LOAD  ACTIVE  SUB  DESCRIPTION
            lines = r.stdout.strip().splitlines()
            active = any(" active " in line or line.split()[2] == "active"
                         for line in lines if line.strip())
            if active:
                return CheckResult(
                    name="systemd_unit",
                    status=CheckStatus.OK,
                    detail="autostock systemd unit active",
                    severity=Severity.CRITICAL,
                )
            return CheckResult(
                name="systemd_unit",
                status=CheckStatus.CRITICAL,
                detail="autostock systemd unit found but not active",
                severity=Severity.CRITICAL,
            )
        except FileNotFoundError:
            return CheckResult(
                name="systemd_unit",
                status=CheckStatus.OK,
                detail="systemctl not available (non-systemd env)",
                severity=Severity.CRITICAL,
            )
        except Exception as e:
            return CheckResult(
                name="systemd_unit",
                status=CheckStatus.WARNING,
                detail=f"systemd check failed: {e}",
                severity=Severity.CRITICAL,
                error=str(e),
            )

    def _check_snapshot_freshness(self) -> CheckResult:
        """steering/snapshot.json published_at within 45s."""
        snap = self.root / "steering" / "snapshot.json"
        if not snap.exists():
            return CheckResult(
                name="snapshot_freshness",
                status=CheckStatus.CRITICAL,
                detail="steering/snapshot.json not found — daemon likely down",
                severity=Severity.CRITICAL,
            )
        try:
            data = json.loads(snap.read_text())
            pub = data.get("published_at")
            if pub is None:
                return CheckResult(
                    name="snapshot_freshness",
                    status=CheckStatus.WARNING,
                    detail="snapshot.json missing published_at field",
                    severity=Severity.CRITICAL,
                )
            # published_at is an ISO timestamp string
            pub_ts = _parse_iso(pub)
            if pub_ts is None:
                return CheckResult(
                    name="snapshot_freshness",
                    status=CheckStatus.WARNING,
                    detail=f"Cannot parse published_at: {pub}",
                    severity=Severity.CRITICAL,
                )
            age_s = time.time() - pub_ts
            if age_s <= 45:
                return CheckResult(
                    name="snapshot_freshness",
                    status=CheckStatus.OK,
                    detail=f"Snapshot fresh ({age_s:.0f}s ago)",
                    severity=Severity.CRITICAL,
                )
            elif age_s <= 120:
                return CheckResult(
                    name="snapshot_freshness",
                    status=CheckStatus.ERROR,
                    detail=f"Snapshot stale ({age_s:.0f}s ago)",
                    severity=Severity.CRITICAL,
                )
            else:
                return CheckResult(
                    name="snapshot_freshness",
                    status=CheckStatus.CRITICAL,
                    detail=f"Snapshot very stale ({age_s:.0f}s ago) — daemon frozen or dead",
                    severity=Severity.CRITICAL,
                )
        except Exception as e:
            return CheckResult(
                name="snapshot_freshness",
                status=CheckStatus.ERROR,
                detail=f"Failed to read snapshot: {e}",
                severity=Severity.CRITICAL,
                error=str(e),
            )

    def _check_monitor_freshness(self) -> CheckResult:
        """steering/monitor.json updated within 60s."""
        mon = self.root / "steering" / "monitor.json"
        if not mon.exists():
            return CheckResult(
                name="monitor_freshness",
                status=CheckStatus.OK,
                detail="steering/monitor.json not found (steering may be off)",
                severity=Severity.WARNING,
            )
        try:
            age_s = time.time() - mon.stat().st_mtime
            if age_s <= 60:
                return CheckResult(
                    name="monitor_freshness",
                    status=CheckStatus.OK,
                    detail=f"Monitor fresh ({age_s:.0f}s ago)",
                    severity=Severity.WARNING,
                )
            return CheckResult(
                name="monitor_freshness",
                status=CheckStatus.WARNING,
                detail=f"Monitor stale ({age_s:.0f}s ago)",
                severity=Severity.WARNING,
            )
        except Exception as e:
            return CheckResult(
                name="monitor_freshness",
                status=CheckStatus.ERROR,
                detail=f"Failed to stat monitor: {e}",
                severity=Severity.WARNING,
                error=str(e),
            )

    def _check_run_state(self) -> CheckResult:
        """workspace/run_state.json — paused or entries_halted?"""
        rs = self.root / "workspace" / "run_state.json"
        if not rs.exists():
            return CheckResult(
                name="run_state",
                status=CheckStatus.OK,
                detail="run_state.json not found",
                severity=Severity.WARNING,
            )
        try:
            data = json.loads(rs.read_text())
            flags: list[str] = []
            if data.get("paused"):
                flags.append("PAUSED")
            if data.get("entries_halted"):
                flags.append("ENTRIES_HALTED")
            if flags:
                return CheckResult(
                    name="run_state",
                    status=CheckStatus.WARNING,
                    detail=", ".join(flags),
                    severity=Severity.WARNING,
                )
            return CheckResult(
                name="run_state",
                status=CheckStatus.OK,
                detail="Running normally",
                severity=Severity.WARNING,
            )
        except Exception as e:
            return CheckResult(
                name="run_state",
                status=CheckStatus.WARNING,
                detail=f"Failed to read run_state: {e}",
                severity=Severity.WARNING,
                error=str(e),
            )

    def _check_code_version(self) -> CheckResult:
        """Compare snapshot code_version vs git rev-parse HEAD."""
        snap = self.root / "steering" / "snapshot.json"
        if not snap.exists():
            return CheckResult(
                name="code_version",
                status=CheckStatus.OK,
                detail="No snapshot to compare code_version",
                severity=Severity.WARNING,
            )
        try:
            data = json.loads(snap.read_text())
            snap_sha = data.get("code_version")
            if not snap_sha:
                return CheckResult(
                    name="code_version",
                    status=CheckStatus.OK,
                    detail="No code_version in snapshot",
                    severity=Severity.WARNING,
                )
            r = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5,
                cwd=str(self.root),
            )
            head_sha = r.stdout.strip()[:8] if r.returncode == 0 else None
            if head_sha and snap_sha[:8] != head_sha:
                return CheckResult(
                    name="code_version",
                    status=CheckStatus.ERROR,
                    detail=f"Code skew: daemon={snap_sha[:8]} repo={head_sha}",
                    severity=Severity.WARNING,
                )
            return CheckResult(
                name="code_version",
                status=CheckStatus.OK,
                detail=f"Code version matches ({snap_sha[:8]})",
                severity=Severity.WARNING,
            )
        except Exception as e:
            return CheckResult(
                name="code_version",
                status=CheckStatus.WARNING,
                detail=f"Code version check failed: {e}",
                severity=Severity.WARNING,
                error=str(e),
            )


def _parse_iso(ts: str) -> float | None:
    """Parse an ISO-8601 timestamp string to a Unix epoch float.

    Handles both 'Z' suffix and +09:00 / -04:00 timezone offsets.
    Returns None on parse failure.
    """
    import re
    from datetime import datetime, timezone

    ts = ts.strip()
    # Replace Z with +00:00 for fromisoformat compatibility (Python <3.11)
    ts_normalized = ts.replace("Z", "+00:00")
    # Python 3.7+ fromisoformat handles ±HH:MM but not arbitrary formats
    # Use a simple approach: if there's a timezone suffix, parse it
    try:
        # Try standard parsing
        dt = datetime.fromisoformat(ts_normalized)
        return dt.timestamp()
    except ValueError:
        pass

    # Fallback: try parsing with regex for non-standard formats
    try:
        # Handle formats like "2026-06-05T14:30:00.123456+09:00"
        m = re.match(
            r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)([+-]\d{2}:\d{2}|Z)?',
            ts,
        )
        if m:
            dt_str = m.group(1)
            tz_str = (m.group(2) or "Z").replace("Z", "+00:00")
            dt = datetime.fromisoformat(dt_str + tz_str)
            return dt.timestamp()
    except Exception:
        pass
    return None

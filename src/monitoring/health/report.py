"""Health report data models (Pydantic v2).

Reports are plain data — no IO, no side effects. This keeps the contract between
the checkers and the consumer (Claude / alerting) simple and testable.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Severity of a single check — how bad a failure would be."""
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class CheckStatus(str, Enum):
    """Outcome of a single check."""
    OK = "OK"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    SKIPPED = "SKIPPED"


class CheckResult(BaseModel):
    """Result of one atomic health check."""
    name: str
    status: CheckStatus
    detail: str = ""
    severity: Severity = Severity.INFO
    duration_ms: float = 0.0
    error: str | None = None


class DimensionResult(BaseModel):
    """Aggregated result for one health dimension (e.g. 'broker')."""
    dimension: str
    status: CheckStatus = CheckStatus.OK
    checks: list[CheckResult] = Field(default_factory=list)

    @property
    def worst_status(self) -> CheckStatus:
        """Derive the dimension status from its sub-checks (worst wins)."""
        if not self.checks:
            return CheckStatus.OK
        severity_order = [
            CheckStatus.OK,
            CheckStatus.SKIPPED,
            CheckStatus.WARNING,
            CheckStatus.ERROR,
            CheckStatus.CRITICAL,
        ]
        worst = self.checks[0].status
        for c in self.checks[1:]:
            if severity_order.index(c.status) > severity_order.index(worst):
                worst = c.status
        return worst


class HealthReport(BaseModel):
    """Top-level health report after running all checks."""
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    ts: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    duration_ms: float = 0.0
    overall: CheckStatus = CheckStatus.OK
    summary: str = ""
    dimensions: dict[str, DimensionResult] = Field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        """Map overall status to a shell exit code."""
        mapping = {
            CheckStatus.OK: 0,
            CheckStatus.WARNING: 1,
            CheckStatus.ERROR: 2,
            CheckStatus.CRITICAL: 3,
            CheckStatus.SKIPPED: 0,
        }
        return mapping.get(self.overall, 0)

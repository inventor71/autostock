"""Risk compliance checks — circuit breakers, stop distance, short gate, approvals."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from src.monitoring.health.checker import BaseChecker
from src.monitoring.health.report import CheckResult, CheckStatus, Severity


class RiskChecker(BaseChecker):
    dimension = "risk"

    def __init__(self, settings):
        self._settings = settings
        self._root = Path(__file__).parent.parent.parent.parent.parent

    def check(self) -> list[CheckResult]:
        results: list[CheckResult] = []

        results.append(self._check_circuit_breaker())
        results.append(self._check_short_gate())
        results.append(self._check_pending_approvals())

        return results

    # ------------------------------------------------------------------
    # individual checks
    # ------------------------------------------------------------------

    def _check_circuit_breaker(self) -> CheckResult:
        """Check if SPY day-change exceeds market_halt_threshold_pct."""
        t0 = time.monotonic()
        try:
            halt_pct = self._settings.risk.market_halt_threshold_pct
            # Fetch SPY daily change via yfinance (fast, no auth needed)
            import yfinance as yf
            spy = yf.Ticker("SPY")
            prev_close = spy.fast_info.get("previous_close") or spy.fast_info.get("regularMarketPreviousClose")
            last_price = spy.fast_info.get("last_price") or spy.fast_info.get("regularMarketPrice")
            if prev_close and last_price:
                chg_pct = (last_price / prev_close - 1)
                elapsed = (time.monotonic() - t0) * 1000
                if chg_pct <= halt_pct:
                    return CheckResult(
                        name="circuit_breaker",
                        status=CheckStatus.WARNING,
                        detail=f"SPY {chg_pct:+.1%} ≤ halt threshold {halt_pct:+.0%} — new buys halted",
                        severity=Severity.WARNING,
                        duration_ms=elapsed,
                    )
                return CheckResult(
                    name="circuit_breaker",
                    status=CheckStatus.OK,
                    detail=f"SPY {chg_pct:+.1%} (halt at {halt_pct:+.0%})",
                    severity=Severity.WARNING,
                    duration_ms=elapsed,
                )
            return CheckResult(
                name="circuit_breaker",
                status=CheckStatus.OK,
                detail="SPY price data unavailable — cannot assess circuit breaker",
                severity=Severity.WARNING,
            )
        except Exception as e:
            return CheckResult(
                name="circuit_breaker",
                status=CheckStatus.WARNING,
                detail=f"Circuit breaker check failed: {e}",
                severity=Severity.WARNING,
                error=str(e),
            )

    def _check_short_gate(self) -> CheckResult:
        """If shorting_enabled is false, verify no open short positions."""
        if self._settings.risk.shorting_enabled:
            return CheckResult(
                name="short_gate",
                status=CheckStatus.OK,
                detail="Shorting enabled",
                severity=Severity.WARNING,
            )
        try:
            from main import create_broker
            broker = create_broker(self._settings)
            positions = broker.get_all_positions()
            short_positions = [p for p in positions if p.qty < 0] if positions else []
            if short_positions:
                syms = ", ".join(p.symbol for p in short_positions)
                return CheckResult(
                    name="short_gate",
                    status=CheckStatus.ERROR,
                    detail=f"SHORTING DISABLED but {len(short_positions)} short positions exist: {syms}",
                    severity=Severity.ERROR,
                )
            return CheckResult(
                name="short_gate",
                status=CheckStatus.OK,
                detail="Shorting disabled, no short positions",
                severity=Severity.WARNING,
            )
        except Exception as e:
            return CheckResult(
                name="short_gate",
                status=CheckStatus.WARNING,
                detail=f"Short gate check failed: {e}",
                severity=Severity.WARNING,
                error=str(e),
            )

    def _check_pending_approvals(self) -> CheckResult:
        """Count pending human approvals in workspace."""
        pa = self._root / "workspace" / "pending_approvals.json"
        if not pa.exists():
            return CheckResult(
                name="pending_approvals",
                status=CheckStatus.OK,
                detail="No pending_approvals.json",
                severity=Severity.WARNING,
            )
        try:
            data = json.loads(pa.read_text())
            count = len(data) if isinstance(data, list) else 0
            if count > 5:
                return CheckResult(
                    name="pending_approvals",
                    status=CheckStatus.WARNING,
                    detail=f"{count} pending approvals — backlog",
                    severity=Severity.WARNING,
                )
            status = CheckStatus.OK if count == 0 else CheckStatus.WARNING
            detail = f"{count} pending approvals" if count else "No pending approvals"
            return CheckResult(
                name="pending_approvals",
                status=status,
                detail=detail,
                severity=Severity.WARNING,
            )
        except Exception as e:
            return CheckResult(
                name="pending_approvals",
                status=CheckStatus.WARNING,
                detail=f"Approval read failed: {e}",
                severity=Severity.WARNING,
                error=str(e),
            )

"""Broker connectivity checks — Alpaca / BrokerAPI account, market, orders."""
from __future__ import annotations

import time

from src.monitoring.health.checker import BaseChecker
from src.monitoring.health.report import CheckResult, CheckStatus, Severity


class BrokerChecker(BaseChecker):
    dimension = "broker"

    def __init__(self, settings):
        self._settings = settings

    def check(self) -> list[CheckResult]:
        results: list[CheckResult] = []

        results.append(self._check_connectivity())
        results.append(self._check_market_open())
        results.append(self._check_open_orders())

        return results

    # ------------------------------------------------------------------
    # individual checks
    # ------------------------------------------------------------------

    def _check_connectivity(self) -> CheckResult:
        """Call broker.get_portfolio_state() — proves auth + account reachable."""
        t0 = time.monotonic()
        try:
            from main import create_broker
            broker = create_broker(self._settings)
            pf = broker.get_portfolio_state()
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="connectivity",
                status=CheckStatus.OK,
                detail=f"Broker OK — equity=${pf.equity:,.0f}, {pf.position_count} positions",
                severity=Severity.ERROR,
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="connectivity",
                status=CheckStatus.ERROR,
                detail=f"Broker unreachable: {e}",
                severity=Severity.ERROR,
                duration_ms=elapsed,
                error=str(e),
            )

    def _check_market_open(self) -> CheckResult:
        """Check market clock."""
        t0 = time.monotonic()
        try:
            from main import create_broker
            broker = create_broker(self._settings)
            is_open = broker.is_market_open()
            elapsed = (time.monotonic() - t0) * 1000
            state = "OPEN" if is_open else "CLOSED"
            return CheckResult(
                name="market_clock",
                status=CheckStatus.OK,
                detail=f"Market {state}",
                severity=Severity.INFO,
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="market_clock",
                status=CheckStatus.WARNING,
                detail=f"Market clock check failed: {e}",
                severity=Severity.INFO,
                duration_ms=elapsed,
                error=str(e),
            )

    def _check_open_orders(self) -> CheckResult:
        """Count resting (open) orders."""
        t0 = time.monotonic()
        try:
            from main import create_broker
            broker = create_broker(self._settings)
            orders = broker.get_open_orders()
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="open_orders",
                status=CheckStatus.OK,
                detail=f"{len(orders)} resting orders",
                severity=Severity.WARNING,
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="open_orders",
                status=CheckStatus.WARNING,
                detail=f"Open orders check failed: {e}",
                severity=Severity.WARNING,
                duration_ms=elapsed,
                error=str(e),
            )

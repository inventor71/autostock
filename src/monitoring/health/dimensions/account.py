"""Account health checks — equity, position count, concentration, P&L."""
from __future__ import annotations

import time

from src.monitoring.health.checker import BaseChecker
from src.monitoring.health.report import CheckResult, CheckStatus, Severity


class AccountChecker(BaseChecker):
    dimension = "account"

    def __init__(self, settings):
        self._settings = settings

    def check(self) -> list[CheckResult]:
        results: list[CheckResult] = []

        pf = None
        try:
            from main import create_broker
            broker = create_broker(self._settings)
            pf = broker.get_portfolio_state()
        except Exception:
            pass

        results.append(self._check_equity(pf))
        results.append(self._check_position_count(pf))
        results.append(self._check_concentration(pf))
        results.append(self._check_unrealized_pnl(pf))

        return results

    # ------------------------------------------------------------------
    # individual checks
    # ------------------------------------------------------------------

    def _check_equity(self, pf) -> CheckResult:
        """Portfolio equity must be positive."""
        if pf is None:
            return self._skipped("equity", "No portfolio state")
        equity = pf.equity
        if equity <= 0:
            return CheckResult(
                name="equity",
                status=CheckStatus.CRITICAL,
                detail=f"Equity ${equity:,.0f} — zero or negative!",
                severity=Severity.CRITICAL,
            )
        return CheckResult(
            name="equity",
            status=CheckStatus.OK,
            detail=f"Equity ${equity:,.0f}, cash ${pf.cash:,.0f}",
            severity=Severity.WARNING,
        )

    def _check_position_count(self, pf) -> CheckResult:
        """Position count vs max_open_positions."""
        if pf is None:
            return self._skipped("position_count", "No portfolio state")
        max_pos = self._settings.risk.max_open_positions
        count = pf.position_count
        if count >= max_pos:
            return CheckResult(
                name="position_count",
                status=CheckStatus.WARNING,
                detail=f"{count}/{max_pos} positions — at limit",
                severity=Severity.WARNING,
            )
        return CheckResult(
            name="position_count",
            status=CheckStatus.OK,
            detail=f"{count}/{max_pos} positions",
            severity=Severity.WARNING,
        )

    def _check_concentration(self, pf) -> CheckResult:
        """Largest position vs max_position_pct * 2 (early-warning threshold)."""
        if pf is None:
            return self._skipped("concentration", "No portfolio state")
        if not pf.positions:
            return CheckResult(
                name="concentration",
                status=CheckStatus.OK,
                detail="No positions",
                severity=Severity.WARNING,
            )
        max_pct = self._settings.risk.max_position_pct
        equity = pf.equity
        biggest = max(pf.positions.values(), key=lambda p: p.market_value)
        pct = biggest.market_value / equity if equity > 0 else 0
        sym = biggest.symbol if hasattr(biggest, 'symbol') else '?'
        if pct > max_pct * 2:
            return CheckResult(
                name="concentration",
                status=CheckStatus.ERROR,
                detail=f"{sym} {pct:.1%} of equity — well above {max_pct:.0%} limit",
                severity=Severity.WARNING,
            )
        elif pct > max_pct:
            return CheckResult(
                name="concentration",
                status=CheckStatus.WARNING,
                detail=f"{sym} {pct:.1%} of equity — above {max_pct:.0%} limit",
                severity=Severity.WARNING,
            )
        return CheckResult(
            name="concentration",
            status=CheckStatus.OK,
            detail=f"Max position {sym} {pct:.1%} of equity",
            severity=Severity.WARNING,
        )

    def _check_unrealized_pnl(self, pf) -> CheckResult:
        """Total unrealized P&L relative to equity."""
        if pf is None:
            return self._skipped("unrealized_pnl", "No portfolio state")
        if not pf.positions:
            return CheckResult(
                name="unrealized_pnl",
                status=CheckStatus.OK,
                detail="No open positions",
                severity=Severity.WARNING,
            )
        total_pnl = sum(p.unrealized_pnl for p in pf.positions.values())
        equity = pf.equity
        pnl_pct = total_pnl / equity if equity > 0 else 0
        if pnl_pct < -0.10:
            return CheckResult(
                name="unrealized_pnl",
                status=CheckStatus.ERROR,
                detail=f"Open P&L {pnl_pct:.1%} — severe drawdown",
                severity=Severity.ERROR,
            )
        elif pnl_pct < -0.05:
            return CheckResult(
                name="unrealized_pnl",
                status=CheckStatus.WARNING,
                detail=f"Open P&L {pnl_pct:.1%} — moderate drawdown",
                severity=Severity.WARNING,
            )
        sign = "+" if total_pnl >= 0 else ""
        return CheckResult(
            name="unrealized_pnl",
            status=CheckStatus.OK,
            detail=f"Open P&L {sign}${total_pnl:,.0f} ({pnl_pct:+.1%})",
            severity=Severity.WARNING,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _skipped(name: str, reason: str) -> CheckResult:
        return CheckResult(
            name=name,
            status=CheckStatus.SKIPPED,
            detail=reason,
            severity=Severity.WARNING,
        )

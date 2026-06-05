"""Data pipeline checks — market data provider connectivity and latency."""
from __future__ import annotations

import time

from src.monitoring.health.checker import BaseChecker
from src.monitoring.health.report import CheckResult, CheckStatus, Severity


class DataPipelineChecker(BaseChecker):
    dimension = "data_pipeline"

    def __init__(self, settings):
        self._settings = settings

    def check(self) -> list[CheckResult]:
        results: list[CheckResult] = []

        # Primary provider (alpaca or yfinance)
        results.append(self._check_primary_provider())

        # YFinance fallback (always available)
        results.append(self._check_yfinance())

        return results

    # ------------------------------------------------------------------
    # individual checks
    # ------------------------------------------------------------------

    def _check_primary_provider(self) -> CheckResult:
        """Fetch one latest price via the configured data provider."""
        t0 = time.monotonic()
        try:
            from main import create_data_provider
            provider = create_data_provider(self._settings)
            price = provider.get_latest_price("SPY")
            elapsed = (time.monotonic() - t0) * 1000
            latency_note = ""
            if elapsed > 2000:
                latency_note = f" (SLOW: {elapsed:.0f}ms)"
            return CheckResult(
                name="primary_provider",
                status=CheckStatus.OK,
                detail=f"{self._settings.data.provider}: SPY=${price:.2f}{latency_note}",
                severity=Severity.ERROR,
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="primary_provider",
                status=CheckStatus.ERROR,
                detail=f"{self._settings.data.provider} unreachable: {e}",
                severity=Severity.ERROR,
                duration_ms=elapsed,
                error=str(e),
            )

    def _check_yfinance(self) -> CheckResult:
        """YFinance fallback check (only if primary is alpaca)."""
        if self._settings.data.provider == "yfinance":
            return CheckResult(
                name="yfinance_fallback",
                status=CheckStatus.OK,
                detail="Primary provider is already yfinance",
                severity=Severity.WARNING,
            )
        t0 = time.monotonic()
        try:
            import yfinance as yf  # noqa: F811
            ticker = yf.Ticker("SPY")
            price = ticker.fast_info.get("last_price") or ticker.fast_info.get("regularMarketPrice")
            elapsed = (time.monotonic() - t0) * 1000
            if price is None:
                return CheckResult(
                    name="yfinance_fallback",
                    status=CheckStatus.WARNING,
                    detail="YFinance returned no price for SPY",
                    severity=Severity.WARNING,
                    duration_ms=elapsed,
                )
            return CheckResult(
                name="yfinance_fallback",
                status=CheckStatus.OK,
                detail=f"YFinance: SPY=${price:.2f}",
                severity=Severity.WARNING,
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="yfinance_fallback",
                status=CheckStatus.WARNING,
                detail=f"YFinance unreachable: {e}",
                severity=Severity.WARNING,
                duration_ms=elapsed,
                error=str(e),
            )

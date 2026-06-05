"""LLM health checks — API connectivity, CLI availability, today's cost."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from src.monitoring.health.checker import BaseChecker
from src.monitoring.health.report import CheckResult, CheckStatus, Severity


class LLMChecker(BaseChecker):
    dimension = "llm"

    def __init__(self, settings):
        self._settings = settings

    def check(self) -> list[CheckResult]:
        results: list[CheckResult] = []

        provider = self._settings.llm.provider

        if provider == "claude":
            results.append(self._check_claude_api())
        elif provider == "claude_code":
            results.append(self._check_claude_cli())
        elif provider == "openai":
            results.append(self._check_openai_api())
        else:
            results.append(CheckResult(
                name="llm_unknown_provider",
                status=CheckStatus.WARNING,
                detail=f"Unknown LLM provider: {provider}",
                severity=Severity.ERROR,
            ))

        # Cost tracking from monitor.json (works regardless of provider)
        results.append(self._check_cost())

        return results

    # ------------------------------------------------------------------
    # individual checks
    # ------------------------------------------------------------------

    def _check_claude_api(self) -> CheckResult:
        """Minimal Anthropic API call (max_tokens=1, trivial prompt)."""
        t0 = time.monotonic()
        try:
            from anthropic import Anthropic
            api_key = self._settings.anthropic_api_key
            if not api_key:
                return CheckResult(
                    name="claude_api",
                    status=CheckStatus.ERROR,
                    detail="ANTHROPIC_API_KEY not set",
                    severity=Severity.ERROR,
                )
            client = Anthropic(api_key=api_key)
            model = self._settings.llm.model or "claude-sonnet-4-6"
            resp = client.messages.create(
                model=model,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="claude_api",
                status=CheckStatus.OK,
                detail=f"Claude API ({model}) OK ({elapsed:.0f}ms)",
                severity=Severity.ERROR,
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="claude_api",
                status=CheckStatus.ERROR,
                detail=f"Claude API unreachable: {e}",
                severity=Severity.ERROR,
                duration_ms=elapsed,
                error=str(e),
            )

    def _check_claude_cli(self) -> CheckResult:
        """Check claude CLI is on PATH and authenticated."""
        t0 = time.monotonic()
        try:
            cli_path = shutil.which("claude")
            if cli_path is None:
                return CheckResult(
                    name="claude_cli",
                    status=CheckStatus.ERROR,
                    detail="claude CLI not on PATH",
                    severity=Severity.WARNING,
                )
            # Just check version — quick, no API cost
            import subprocess
            r = subprocess.run(
                [cli_path, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            elapsed = (time.monotonic() - t0) * 1000
            version = r.stdout.strip().split("\n")[0] if r.stdout.strip() else "unknown"
            if r.returncode == 0:
                return CheckResult(
                    name="claude_cli",
                    status=CheckStatus.OK,
                    detail=f"Claude CLI {version} ({elapsed:.0f}ms)",
                    severity=Severity.WARNING,
                    duration_ms=elapsed,
                )
            return CheckResult(
                name="claude_cli",
                status=CheckStatus.WARNING,
                detail=f"Claude CLI returned {r.returncode}: {r.stderr[:120]}",
                severity=Severity.WARNING,
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="claude_cli",
                status=CheckStatus.ERROR,
                detail=f"Claude CLI check failed: {e}",
                severity=Severity.WARNING,
                duration_ms=elapsed,
                error=str(e),
            )

    def _check_openai_api(self) -> CheckResult:
        """Minimal OpenAI API call."""
        t0 = time.monotonic()
        try:
            from openai import OpenAI
            api_key = self._settings.openai_api_key
            if not api_key:
                return CheckResult(
                    name="openai_api",
                    status=CheckStatus.ERROR,
                    detail="OPENAI_API_KEY not set",
                    severity=Severity.ERROR,
                )
            client = OpenAI(api_key=api_key)
            model = self._settings.llm.model or "gpt-4o"
            client.chat.completions.create(
                model=model,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="openai_api",
                status=CheckStatus.OK,
                detail=f"OpenAI ({model}) OK ({elapsed:.0f}ms)",
                severity=Severity.ERROR,
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="openai_api",
                status=CheckStatus.ERROR,
                detail=f"OpenAI API unreachable: {e}",
                severity=Severity.ERROR,
                duration_ms=elapsed,
                error=str(e),
            )

    def _check_cost(self) -> CheckResult:
        """Read today's turn cost from steering/monitor.json."""
        mon = self.root / "steering" / "monitor.json"
        if not mon.exists():
            return CheckResult(
                name="turn_cost",
                status=CheckStatus.OK,
                detail="No monitor.json — steering may be off",
                severity=Severity.INFO,
            )
        try:
            data = json.loads(mon.read_text())
            turns = data.get("turns", {})
            count = turns.get("today_count", 0)
            cost = turns.get("today_cost_usd", 0.0)
            return CheckResult(
                name="turn_cost",
                status=CheckStatus.OK,
                detail=f"{count} turns today, ${cost:.2f} total",
                severity=Severity.INFO,
            )
        except Exception as e:
            return CheckResult(
                name="turn_cost",
                status=CheckStatus.WARNING,
                detail=f"Cost read failed: {e}",
                severity=Severity.INFO,
                error=str(e),
            )

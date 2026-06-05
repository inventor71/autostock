"""Configuration and environment validation."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

from src.monitoring.health.checker import BaseChecker
from src.monitoring.health.report import CheckResult, CheckStatus, Severity


class ConfigEnvChecker(BaseChecker):
    dimension = "config_env"

    # Env vars that must be set depending on provider choice
    ESSENTIAL_ENV = [
        "ALPACA_API_KEY",
        "ALPACA_API_SECRET",
    ]

    LLM_ENV_MAP = {
        "claude": ["ANTHROPIC_API_KEY"],
        "openai": ["OPENAI_API_KEY"],
        "claude_code": [],  # uses logged-in CLI session
    }

    def __init__(self, settings):
        self._settings = settings

    def check(self) -> list[CheckResult]:
        results: list[CheckResult] = []

        results.append(self._check_env_vars())
        results.append(self._check_settings_yaml())
        results.append(self._check_dotenv())

        return results

    # ------------------------------------------------------------------
    # individual checks
    # ------------------------------------------------------------------

    def _check_env_vars(self) -> CheckResult:
        """Check essential settings values are populated (from env or .env).

        Uses pydantic-settings attribute access rather than os.environ because
        values may be loaded from a .env file (not exported into os.environ).
        """
        missing: list[str] = []
        s = self._settings

        # Always-needed broker keys — checked via settings attributes
        if not s.alpaca_api_key:
            missing.append("ALPACA_API_KEY")
        if not s.alpaca_api_secret:
            missing.append("ALPACA_API_SECRET")

        # LLM-specific keys
        provider = s.llm.provider
        if provider == "claude" and not s.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        elif provider == "openai" and not s.openai_api_key:
            missing.append("OPENAI_API_KEY")
        # claude_code needs no key

        # Finnhub (optional — earnings provider)
        signals_cfg = s.signals if isinstance(s.signals, dict) else {}
        if signals_cfg.get("enabled", False) and not s.finnhub_api_key:
            pass  # Not blocking — earnings provider is optional

        # Broker API keys (only if provider is broker_api)
        if s.broker.provider == "broker_api":
            if not s.broker_api_key:
                missing.append("BROKER_API_KEY")
            if not s.broker_api_secret:
                missing.append("BROKER_API_SECRET")

        if missing:
            return CheckResult(
                name="env_vars",
                status=CheckStatus.ERROR,
                detail=f"Missing env vars: {', '.join(missing)}",
                severity=Severity.ERROR,
            )
        return CheckResult(
            name="env_vars",
            status=CheckStatus.OK,
            detail=f"All essential settings present (LLM provider={provider})",
            severity=Severity.ERROR,
        )

    def _check_settings_yaml(self) -> CheckResult:
        """Verify settings.yaml parses correctly."""
        settings_path = self.root / "config" / "settings.yaml"
        if not settings_path.exists():
            return CheckResult(
                name="settings_yaml",
                status=CheckStatus.ERROR,
                detail="config/settings.yaml not found",
                severity=Severity.ERROR,
            )
        try:
            with open(settings_path) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                return CheckResult(
                    name="settings_yaml",
                    status=CheckStatus.ERROR,
                    detail="settings.yaml did not parse as a dict",
                    severity=Severity.ERROR,
                )
            # Quick structural check
            top_keys = {"app", "broker", "data", "trading", "risk", "llm", "agent"}
            present = top_keys & set(data.keys())
            missing = top_keys - set(data.keys())
            if missing:
                return CheckResult(
                    name="settings_yaml",
                    status=CheckStatus.WARNING,
                    detail=f"Parsed OK but missing top-level keys: {', '.join(sorted(missing))}",
                    severity=Severity.ERROR,
                )
            return CheckResult(
                name="settings_yaml",
                status=CheckStatus.OK,
                detail=f"settings.yaml valid ({len(data)} top-level sections)",
                severity=Severity.ERROR,
            )
        except yaml.YAMLError as e:
            return CheckResult(
                name="settings_yaml",
                status=CheckStatus.ERROR,
                detail=f"YAML parse error: {e}",
                severity=Severity.ERROR,
                error=str(e),
            )

    def _check_dotenv(self) -> CheckResult:
        """Check .env file exists and is readable."""
        env_path = os.environ.get("AUTOSTOCK_ENV_FILE") or str(self.root / ".env")
        p = Path(env_path)
        if not p.exists():
            return CheckResult(
                name="dotenv",
                status=CheckStatus.WARNING,
                detail=f".env not found at {p}",
                severity=Severity.WARNING,
            )
        try:
            with open(p) as f:
                lines = f.readlines()
            # Count non-empty, non-comment lines
            count = sum(1 for line in lines if line.strip() and not line.strip().startswith("#"))
            return CheckResult(
                name="dotenv",
                status=CheckStatus.OK,
                detail=f".env OK ({count} entries) at {p}",
                severity=Severity.WARNING,
            )
        except Exception as e:
            return CheckResult(
                name="dotenv",
                status=CheckStatus.ERROR,
                detail=f"Cannot read .env: {e}",
                severity=Severity.WARNING,
                error=str(e),
            )

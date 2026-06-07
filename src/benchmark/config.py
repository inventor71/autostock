from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

# Default baseline set (D2): buy & hold + the four technical strategies. ML is
# out of scope (no training pipeline / model files — would sit at HOLD forever).
DEFAULT_BASELINES = ["buy_and_hold", "ma_crossover", "rsi", "macd", "bollinger"]


@dataclass
class BenchmarkConfig:
    """Parsed ``benchmark:`` settings section.

    Master toggle defaults OFF (NFR-1): with no config, nothing runs, no extra
    accounts are touched, the agent path is byte-for-byte unchanged.
    """

    enabled: bool = False
    baselines: list[str] = field(default_factory=lambda: list(DEFAULT_BASELINES))
    accounts: dict[str, str] = field(default_factory=dict)  # strategy -> sandbox account_id
    # cadence: "eod" (once daily, default) or a positive integer minute interval.
    interval: str | int = "eod"
    storage_dir: str = "data/benchmark"
    retention_days: int = 365

    @classmethod
    def from_settings(cls, settings) -> "BenchmarkConfig":
        raw = dict(getattr(settings, "benchmark", {}) or {})
        cfg = cls(
            enabled=bool(raw.get("enabled", False)),
            baselines=list(raw.get("baselines") or DEFAULT_BASELINES),
            accounts=dict(raw.get("accounts") or {}),
            interval=raw.get("interval", "eod"),
            storage_dir=raw.get("storage_dir", "data/benchmark"),
            retention_days=int(raw.get("retention_days", 365)),
        )
        if cfg.enabled:
            missing = [b for b in cfg.baselines if b not in cfg.accounts]
            if missing:
                logger.warning(
                    "benchmark: no sandbox account mapped for {} — these baselines "
                    "will be skipped (fail-closed)",
                    missing,
                )
        return cfg

    @property
    def interval_minutes(self) -> int | None:
        """Minute interval, or None for end-of-day cadence."""
        if isinstance(self.interval, str) and self.interval.lower() == "eod":
            return None
        try:
            m = int(self.interval)
            return m if m > 0 else None
        except (TypeError, ValueError):
            return None

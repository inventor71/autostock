"""Configuration for early-session signal detection.

Loaded from ``config/settings.yaml`` → ``early_session:`` block.
See ``src/early_session/config.py`` in the F51 design.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EarlySessionConfig(BaseModel):
    """Early-session detection parameters. All fields are configurable."""

    enabled: bool = True
    threshold_pct: float = Field(default=5.0, description="±% trigger threshold (Q1=D)")
    window_minutes: int = Field(default=10, description="Detection lookback window in minutes (Q1=D)")
    dump_before_minutes: int = Field(default=15, description="Minutes of bars to dump BEFORE detection (Q2=C)")
    dump_after_minutes: int = Field(default=45, description="Minutes of bars to dump AFTER detection (Q2=C)")
    poll_interval_seconds: int = Field(default=30, description="Seconds between bar-fetch ticks")
    buffer_retention_minutes: int = Field(default=20, description="How many minutes of bars the circular buffer retains")
    monitor_start_et: str = Field(default="09:30", description="ET time to start monitoring (HH:MM)")
    monitor_end_et: str = Field(default="10:30", description="ET time to stop monitoring (HH:MM)")

    # Margin (minutes) added on top of the dump window when deriving the buffer
    # retention floor, so a slightly late finalize still finds its bars.
    _RETENTION_MARGIN_MIN: int = 5

    @property
    def effective_retention_minutes(self) -> int:
        """Buffer retention that is guaranteed to cover the whole dump window.

        The circular buffer must retain bars from ``dump_before`` minutes before a
        trigger through ``dump_after`` minutes after it (plus the detection window
        and a small margin), otherwise the finalize step dumps a truncated
        after-window. We take the max of the configured value and that floor so a
        too-small ``buffer_retention_minutes`` can never silently drop data.
        """
        floor = (
            self.dump_before_minutes
            + self.dump_after_minutes
            + self.window_minutes
            + self._RETENTION_MARGIN_MIN
        )
        return max(self.buffer_retention_minutes, floor)

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> EarlySessionConfig:
        """Create config from the parsed settings dict (``config/settings.yaml``)."""
        block = settings.get("early_session", {})
        if not block:
            return cls()
        return cls(**{k: v for k, v in block.items() if k in cls.model_fields})

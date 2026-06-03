"""Surge detection configuration from settings.yaml."""

from pydantic import BaseModel, Field


class SurgeDetectionConfig(BaseModel):
    """Configuration for the surge detector.

    Loaded from ``config/settings.yaml`` → ``surge:`` block.
    """

    threshold_pct: float = Field(
        default=7.0,
        ge=0.0,
        description="Absolute percent change to qualify as surge/dive (default 7%)",
    )
    min_volume: int = Field(
        default=0,
        ge=0,
        description="Minimum daily volume (0 = no minimum)",
    )

    @classmethod
    def from_settings(cls, settings: dict) -> "SurgeDetectionConfig":
        """Create config from the parsed settings dict."""
        surge_block = settings.get("surge", {})
        if not surge_block:
            return cls()
        return cls(**surge_block)

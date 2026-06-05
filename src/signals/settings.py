"""Market-signal configuration from settings.yaml ``signals:`` block (F61, FR-7)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SignalSources(BaseModel):
    news_primary: Literal["alpaca", "yfinance"] = "alpaca"
    news_fallback: Literal["yfinance", "none"] = "yfinance"
    earnings_provider: Literal["finnhub", "none"] = "finnhub"


class SignalsConfig(BaseModel):
    """Loaded from ``config/settings.yaml`` → ``signals:`` block.

    All thresholds/maps/lists live here, not in code (FR-7). Sensible seed
    defaults so the subsystem works even with an empty block.
    """

    enabled: bool = True

    # Mover thresholds (R1)
    price_pct: float = Field(default=5.0, ge=0.0)
    vol_ratio: float = Field(default=2.0, ge=0.0)
    require: Literal["any", "both"] = "any"
    max_movers: int = Field(default=12, ge=1)

    # Read-through (R2)
    readthrough_min_pct: float = Field(default=7.0, ge=0.0)
    max_peers: int = Field(default=8, ge=1)

    # Earnings (R3)
    earnings_horizon_days: int = Field(default=2, ge=0)

    # Universe extension (R7) — signal-only, never tradeable
    bellwether_watchlist: list[str] = Field(default_factory=list)

    # Peer map (R6): group name -> members
    peer_groups: dict[str, list[str]] = Field(default_factory=dict)

    # Source toggles (R8)
    sources: SignalSources = Field(default_factory=SignalSources)

    # Caching / latency (NFR-2/3)
    cache_ttl_seconds: float = Field(default=300.0, ge=0.0)
    http_connect_timeout: float = Field(default=3.0, gt=0.0)
    http_read_timeout: float = Field(default=5.0, gt=0.0)
    # Aggregate budget for the price scan (yfinance has no per-call bound, so cap
    # the whole scoreboard scan so a slow backend can't stall the research turn).
    scan_timeout_seconds: float = Field(default=30.0, gt=0.0)

    @classmethod
    def from_settings(cls, signals_block: dict | None) -> "SignalsConfig":
        """Create config from the parsed ``signals:`` dict (empty → seed defaults)."""
        if not signals_block:
            return cls()
        return cls(**signals_block)

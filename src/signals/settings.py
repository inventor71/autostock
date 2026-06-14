"""Market-signal configuration from settings.yaml ``signals:`` block (F61, FR-7)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SignalSources(BaseModel):
    news_primary: Literal["alpaca", "yfinance"] = "alpaca"
    news_fallback: Literal["yfinance", "none"] = "yfinance"
    earnings_provider: Literal["finnhub", "none"] = "finnhub"
    ipo_provider: Literal["finnhub", "none"] = "finnhub"  # F78


class DisclosedHoldingsConfig(BaseModel):
    """Disclosed-holdings ingestion (F81) — source-agnostic, providers listed below.

    The daemon refresher does the only HTTP (every ``refresh_hours``) and writes a
    normalized snapshot per source to ``workspace/holdings/``; the universe overlay
    and the brief read that cache. Shipped OFF — set ``enabled: true`` to activate.

    Each provider entry is ``{type, ...}`` (type-tagged so a new disclosure source
    plugs in without touching the consumers): for ``sec_13f`` →
    ``{type: sec_13f, cik, manager_name?, overlay?}``.
    """

    enabled: bool = False
    refresh_hours: float = Field(default=24.0, gt=0.0)  # FR-7 poll cadence (13F is quarterly)
    max_age_days: int = Field(default=135, ge=1)        # staleness drop (~1 quarter + 45d lag)
    brief_top_n: int = Field(default=6, ge=1)           # names per side shown in the brief
    # SEC fair-access (NFR-4). Put a real contact in the UA per SEC policy.
    user_agent: str = "autostock/1.0 (contact: ops@example.com)"
    request_gap_s: float = Field(default=0.5, ge=0.0)
    http_connect_timeout: float = Field(default=3.0, gt=0.0)
    http_read_timeout: float = Field(default=10.0, gt=0.0)
    cusip_map_path: str = "config/holdings/cusip_ticker.json"
    providers: list[dict] = Field(default_factory=list)


class SentimentConfig(BaseModel):
    """Retail sentiment sweep + outlier selection (F77).

    The sweep is plain HTTP against StockTwits' unauthenticated symbol streams
    (no LLM cost). All knobs live here, not in code (FR-7 precedent)."""

    enabled: bool = True
    sweep_minutes: int = Field(default=60, ge=1)
    # Sweep only inside this ET window (extended-hours session).
    window_et: tuple[str, str] = ("04:00", "20:00")
    request_gap_s: float = Field(default=0.5, ge=0.0)
    # Hard cap on requests per sweep tick — stays inside StockTwits'
    # ~200/hr unauthenticated allowance with retry headroom (NFR-3).
    hourly_budget: int = Field(default=150, ge=1)
    baseline_days: int = Field(default=5, ge=1)
    # A symbol needs this many history points before it can be an outlier
    # (cold-start cut) and this many currently tagged messages (small-sample cut).
    min_baseline_points: int = Field(default=12, ge=1)
    min_tagged: int = Field(default=8, ge=0)
    top_k: int = Field(default=5, ge=1)
    z_threshold: float = Field(default=2.0, ge=0.0)
    # Ignore a 'current' point older than this (sweep stopped → no stale outliers).
    max_age_minutes: int = Field(default=180, ge=1)


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
    # Cap the per-trigger news lookups used to fill cause_hint, so a volatile day
    # with many alerts can't fan out into an unbounded news call count.
    max_cause_hint_lookups: int = Field(default=5, ge=0)

    # Earnings (R3)
    earnings_horizon_days: int = Field(default=2, ge=0)

    # Imminent IPOs / catalysts (F78) — awareness channel, never universe-filtered.
    # Slightly longer horizon than earnings so a listing a few days out is visible.
    ipo_horizon_days: int = Field(default=5, ge=0)
    max_ipos: int = Field(default=8, ge=1)  # brief cap (keep the push compact)

    # Universe extension (R7) — signal-only, never tradeable
    bellwether_watchlist: list[str] = Field(default_factory=list)

    # Peer map (R6): group name -> members
    peer_groups: dict[str, list[str]] = Field(default_factory=dict)

    # Source toggles (R8)
    sources: SignalSources = Field(default_factory=SignalSources)

    # Retail sentiment (F77)
    sentiment: SentimentConfig = Field(default_factory=SentimentConfig)

    # Disclosed holdings (F81) — institutional 13F → universe overlay + brief
    disclosed_holdings: DisclosedHoldingsConfig = Field(default_factory=DisclosedHoldingsConfig)

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

"""Domain entities for market-signal collection (F61).

All records are pydantic models so they serialize round-trip
(``model_validate(x.model_dump()) == x``) — a property covered by PBT-02.
"""

from __future__ import annotations

from datetime import date as _date, datetime
from typing import Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Inputs (normalized rows handed to the pure functions)
# --------------------------------------------------------------------------- #
class MoverRow(BaseModel):
    """One scan row (a scoreboard-style snapshot) fed to ``detect_movers``."""

    symbol: str
    change_pct: float | None = None  # % vs prior close
    volume_ratio: float | None = None  # today vol / 20d avg
    close: float | None = None


class EarningsRow(BaseModel):
    """One earnings-calendar entry fed to ``select_imminent_earnings``."""

    symbol: str
    earnings_date: _date
    when: Literal["bmo", "amc", "unknown"] = "unknown"  # before-open / after-close
    eps_estimate: float | None = None


# --------------------------------------------------------------------------- #
# Peer map (static, config-driven)
# --------------------------------------------------------------------------- #
class PeerGroup(BaseModel):
    """A named group of related tickers (e.g. ``semiconductors``)."""

    name: str
    members: list[str]


# --------------------------------------------------------------------------- #
# Outputs
# --------------------------------------------------------------------------- #
class Mover(BaseModel):
    """A symbol whose price/volume move cleared the mover threshold (FR-1)."""

    symbol: str
    change_pct: float
    volume_ratio: float | None = None
    close: float | None = None
    direction: Literal["up", "down"]
    in_universe: bool
    qualified_by: list[Literal["price", "volume"]]


class ReadThroughAlert(BaseModel):
    """A trigger mover and the universe peers it may read through to (FR-3).

    Python only proposes ``affected_peers``; whether the read-through is real is
    the agent's call (LLM hybrid).
    """

    trigger_symbol: str
    trigger_change_pct: float
    cause_hint: str | None = None
    affected_peers: list[str]
    groups: list[str]


class ImminentEarnings(BaseModel):
    """An upcoming earnings report inside the horizon (FR-4)."""

    symbol: str
    earnings_date: _date
    when: Literal["bmo", "amc", "unknown"] = "unknown"
    eps_estimate: float | None = None
    is_held: bool = False
    peer_readthrough: list[str] = Field(default_factory=list)


class MarketSignalBrief(BaseModel):
    """The unified signal brief shared by the push (prompt) and pull (tools) paths."""

    as_of: datetime = Field(default_factory=datetime.now)
    movers: list[Mover] = Field(default_factory=list)
    readthrough_alerts: list[ReadThroughAlert] = Field(default_factory=list)
    imminent_earnings: list[ImminentEarnings] = Field(default_factory=list)
    degraded_sources: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.movers or self.readthrough_alerts or self.imminent_earnings)

    def to_dict(self) -> dict:
        """JSON-friendly dict for the on-demand tools."""
        return self.model_dump(mode="json")

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


# --------------------------------------------------------------------------- #
# Imminent IPOs / catalysts (F78 — awareness channel, NOT a buy menu)
# --------------------------------------------------------------------------- #
_IpoStatus = Literal["expected", "priced", "withdrawn", "filed", "unknown"]


class IpoRow(BaseModel):
    """One IPO-calendar entry fed to ``select_imminent_ipos`` (F78).

    Symbol may be absent before pricing; ``name`` is the stable identifier.
    ``est_value`` (Finnhub ``totalSharesValue``) is the size proxy used to rank.
    """

    name: str
    symbol: str | None = None
    ipo_date: _date
    exchange: str | None = None
    status: _IpoStatus = "unknown"
    shares: int | None = None
    price_low: float | None = None
    price_high: float | None = None
    est_value: float | None = None


class ImminentIpo(BaseModel):
    """An upcoming IPO inside the horizon (F78, FR-2).

    Unlike earnings, IPOs are NOT filtered to the tradeable universe — the whole
    point is awareness of names not yet a ticker. ``in_universe`` / ``is_held``
    are tags only (a recent IPO already added to the universe), never a filter.
    """

    name: str
    symbol: str | None = None
    ipo_date: _date
    exchange: str | None = None
    status: _IpoStatus = "unknown"
    est_value: float | None = None
    in_universe: bool = False
    is_held: bool = False


# --------------------------------------------------------------------------- #
# Retail sentiment (F77 — StockTwits self-labeled Bullish/Bearish)
# --------------------------------------------------------------------------- #
class SentimentRecord(BaseModel):
    """One symbol's label aggregate from one sweep (a history JSONL line).

    Counts are a snapshot of the symbol stream's most recent messages at sweep
    time, not cumulative totals. No usernames or message bodies are ever stored
    (SECURITY-03 / NFR-4) — the self-declared labels are the whole signal.
    """

    ts: datetime
    symbol: str
    bullish_n: int = Field(ge=0)
    bearish_n: int = Field(ge=0)
    untagged_n: int = Field(ge=0)
    latest_id: int | None = None  # newest message id seen (chatter-volume proxy)

    @property
    def tagged_n(self) -> int:
        return self.bullish_n + self.bearish_n


class SentimentOutlier(BaseModel):
    """A symbol whose current sentiment deviates from its OWN baseline (FR-3).

    StockTwits skews ~75% bullish at rest, so absolute ratios are meaningless;
    only the per-symbol z-scores carry signal.
    """

    symbol: str
    bull_ratio: float  # current bullish/(bullish+bearish), 0..1
    baseline_ratio: float  # baseline mean of the same ratio
    ratio_z: float | None = None
    tagged_n: int = Field(ge=0)
    direction: Literal["bullish", "bearish"]


class MarketSignalBrief(BaseModel):
    """The unified signal brief shared by the push (prompt) and pull (tools) paths."""

    as_of: datetime = Field(default_factory=datetime.now)
    movers: list[Mover] = Field(default_factory=list)
    readthrough_alerts: list[ReadThroughAlert] = Field(default_factory=list)
    imminent_earnings: list[ImminentEarnings] = Field(default_factory=list)
    imminent_ipos: list[ImminentIpo] = Field(default_factory=list)  # F78
    sentiment_outliers: list[SentimentOutlier] = Field(default_factory=list)  # F77
    degraded_sources: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.movers or self.readthrough_alerts or self.imminent_earnings
                    or self.imminent_ipos or self.sentiment_outliers)

    def to_dict(self) -> dict:
        """JSON-friendly dict for the on-demand tools."""
        return self.model_dump(mode="json")

"""Source-agnostic domain entities for disclosed holdings (F81).

All records are pydantic models so they serialize round-trip
(``model_validate(x.model_dump()) == x``) — covered by PBT, same contract as the
F61 signal records. NONE of these types know about 13F/EDGAR: a provider maps its
raw filing into ``HoldingsSnapshot`` and the rest of the system only sees this.
"""

from __future__ import annotations

from datetime import date as _date, datetime
from typing import Literal

from pydantic import BaseModel, Field

# Normalized direction. A long equity/CALL position is bullish (LONG); a PUT is a
# bearish bet (SHORT). The provider does this mapping so downstream code never has
# to reason about put/call — only about the trade direction it implies.
Side = Literal["LONG", "SHORT"]


class HoldingRow(BaseModel):
    """One normalized position from a manager's disclosure.

    Only rows whose underlying could be mapped to a tradeable ticker appear here;
    unmapped rows are counted in ``HoldingsSnapshot.unmapped_n`` instead (so the
    brief can be honest about coverage without inventing tickers).
    """

    ticker: str
    side: Side
    weight: float = Field(ge=0.0)          # share of the manager's disclosed value, 0..1
    value_usd: float | None = None         # position value in USD (provider-normalized)
    shares: int | None = None
    raw_id: str = ""                       # source identifier (e.g. CUSIP) — trace/debug
    # Original direction marker kept for transparency; ``side`` is already normalized.
    put_call: Literal["PUT", "CALL"] | None = None


class HoldingsSnapshot(BaseModel):
    """One manager's holdings as of one filing — the only thing downstream sees."""

    source_id: str                         # e.g. "sec_13f:0002045724" (stable cache key)
    manager_name: str                      # e.g. "Situational Awareness LP"
    as_of: _date                           # filing report date (quarter-end) — staleness basis
    fetched_at: datetime = Field(default_factory=datetime.now)
    accession: str | None = None           # source filing id (13F accession no.) — trace
    rows: list[HoldingRow] = Field(default_factory=list)
    unmapped_n: int = Field(default=0, ge=0)   # rows dropped for want of a ticker mapping

    def long_tickers(self) -> list[str]:
        return [r.ticker for r in self.rows if r.side == "LONG"]

    def short_tickers(self) -> list[str]:
        return [r.ticker for r in self.rows if r.side == "SHORT"]


class HoldingsDiff(BaseModel):
    """Ticker-set change vs the previous snapshot (for the brief's NEW/EXIT lines).

    ``new`` = appeared this filing (both sides), ``exited`` = gone this filing.
    Direction flips (LONG↔SHORT for the same ticker) surface as both an exit and a
    new entry on the respective side lists, which is the honest reading.
    """

    new: list[str] = Field(default_factory=list)
    exited: list[str] = Field(default_factory=list)


class HoldingsHighlight(BaseModel):
    """Compact, render-ready summary of one snapshot for the research brief (FR-5).

    The brief never dumps every holding — it shows the top names per side plus the
    diff, with the direction made explicit so a PUT is never read as bullish.
    """

    source_id: str
    manager_name: str
    as_of: _date
    long_top: list[str] = Field(default_factory=list)
    short_top: list[str] = Field(default_factory=list)
    new: list[str] = Field(default_factory=list)
    exited: list[str] = Field(default_factory=list)
    unmapped_n: int = Field(default=0, ge=0)
    stale: bool = False                    # filing older than the configured max age

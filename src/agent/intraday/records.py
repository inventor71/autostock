"""Pydantic records for the intraday redesign (F3).

All are plain data carriers — the agent never places orders through them
(advisor-only, BR-1). ``WatchTrigger``/``WatchRecord`` are the only persisted
records (append-only ``workspace/watch.jsonl``, written solely by the ``watch``
agent tool, BR-6.1); the rest (``WakeEvent``/``FillEvent``/``SnapshotDelta``/
``NewsDiff``/``AbnormalMoveSignal``) are transient, assembled per turn and never
written to a durable channel.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ---- watch-trigger vocabulary (v1 = A+B; Q2) ------------------------------- #
# A: immediate last-price cross; B: bar/session-close confirmation.
WatchCondition = Literal["price_above", "price_below", "close_above", "close_below"]
CLOSE_CONDITIONS: frozenset[str] = frozenset({"close_above", "close_below"})

# ---- wake-event taxonomy (FR-4) -------------------------------------------- #
WakeKind = Literal["new_fill", "abnormal_move", "watch_trigger", "protective_reassess"]


def _new_id() -> str:
    return uuid.uuid4().hex


class WatchTrigger(BaseModel):
    """E1 — a structured intraday watch the agent registers and Python evaluates.

    ``intent`` is a free-text suggestion (e.g. "ADJUST_STOP->tighten to 180"); it
    is NOT auto-applied — a met condition wakes the LLM to *judge* (FR-5, BR-1).
    ``valid_until`` is an ET calendar date (YYYY-MM-DD); expiry is swept at the
    ET-midnight daily sweep (BR-6.5).
    """

    id: str = Field(default_factory=_new_id)
    symbol: str
    condition: WatchCondition
    level: float
    intent: str = ""
    thesis_ref: str | None = None
    valid_until: str | None = None  # ET date "YYYY-MM-DD"
    created_ts: datetime = Field(default_factory=datetime.now)

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @property
    def is_close_condition(self) -> bool:
        return self.condition in CLOSE_CONDITIONS


class WatchRecord(BaseModel):
    """One append-only line in ``workspace/watch.jsonl``.

    ``kind="set"`` carries a full ``trigger``; ``kind="clear"`` carries only the
    ``target_id`` of a previously-set trigger. State transitions are expressed by
    appending records + a separate fired-id set (BR-6.4), never by rewriting.
    """

    kind: Literal["set", "clear"]
    ts: datetime = Field(default_factory=datetime.now)
    trigger: WatchTrigger | None = None
    target_id: str | None = None

    @model_validator(mode="after")
    def _set_needs_trigger(self) -> WatchRecord:
        if self.kind == "set" and self.trigger is None:
            raise ValueError("kind='set' requires a trigger")
        return self


class FillEvent(BaseModel):
    """E4 — one broker fill event (from the activities cursor, Q3=A).

    Keyed by the broker activity ``id`` (NOT the order id) so partial fills on one
    order stay distinct and the cursor is idempotent (BR-7).
    """

    fill_id: str  # broker activity id (idempotency key)
    symbol: str
    qty: float
    price: float
    side: Literal["buy", "sell"]
    kind: Literal["entry", "protective", "unknown"] = "unknown"
    # tz-aware so a mix of broker (RFC3339 +00:00) and fallback timestamps never
    # raises on max()/comparison in the snapshot cursor (review #3).
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class SnapshotDelta(BaseModel):
    """E4 — what changed since the previous snapshot (new-fill wake + brief delta)."""

    new_fills: list[FillEvent] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)  # new highs/lows, level-proximity changes


class WakeEvent(BaseModel):
    """E3 — a typed, judgement-worthy event handed to a single coalesced wake turn.

    ``entry_inducing`` is the suppression key under ``entries_halted`` (Q7=A):
    True for momentum/entry triggers, dropped when entries are halted; new_fill /
    protective_reassess / sell-side watches stay False and always fire (BR-11).
    """

    kind: WakeKind
    symbol: str
    reason: str
    payload: dict[str, Any] = Field(default_factory=dict)
    detected_ts: datetime = Field(default_factory=datetime.now)
    entry_inducing: bool = False


class AbnormalMoveSignal(BaseModel):
    """E6 — result of the abnormal-move check (ATR multiple OR volume spike, Q4)."""

    symbol: str
    kind: Literal["price", "volume"]
    magnitude: float  # |price move| or volume
    threshold: float  # k*ATR or m*avg
    reason: str = ""


class NewsDiff(BaseModel):
    """E5 — new headlines since the previous turn (scheduled-turn brief only, FR-6)."""

    symbol: str
    headlines: list[str] = Field(default_factory=list)
    last_seen_key: str = ""

"""Pydantic records for the steering channel (E2/E6/E7/E8/E9).

All steering payloads are safe-deserialized pydantic models (SECURITY-13) and
carry no secrets in their serialized form (SECURITY-03) -- with the deliberate
exception of ``SteeringCommand.token``, which is validated by the daemon and
NEVER written to events/logs (see channel.py / BR-10.2).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.agent.journal import Decision

# ---- command grammar ------------------------------------------------------- #
# F9: order verbs are now STRUCTURED (Alpaca-shaped) tool calls; safety/lifecycle
# verbs stay deterministic shorthand (FR-2 hybrid). buy/sell remain as the
# deterministic shorthand the opencode AI may still emit (routed through the same
# RiskManager gate). New structured order/management verbs:
#   place_order   -- full Alpaca-shaped place_stock_order (args = PlaceOrderArgs)
#   cancel_order  -- cancel a specific broker order by id
#   cancel_all    -- cancel all (optionally per-symbol) resting orders
#   replace_order -- modify a resting SIMPLE order (Q2=A: leg replace rejected)
#   close_position / close_all -- close one / all positions
SteeringVerb = Literal[
    "buy", "sell", "flatten", "flatten_all", "stop",
    "pause", "resume", "halt_entries", "allow_entries", "kill",
    "approve", "reject", "unlock", "cancel",
    "note", "directive", "directive_clear", "answer",
    "place_order", "cancel_order", "cancel_all", "replace_order",
    "close_position", "close_all",
]

# verbs that mutate the book / lifecycle and must be confirmed by the operator
# tool before reaching the channel (BR-1'); everything else is context/admin.
TRADE_VERBS: frozenset[str] = frozenset({
    "buy", "sell", "flatten", "flatten_all", "stop",
    "place_order", "close_position", "close_all",
})
EMERGENCY_VERBS: frozenset[str] = frozenset({"kill", "flatten_all", "flatten", "pause", "halt_entries"})


class PlaceOrderArgs(BaseModel):
    """F9 per-verb args schema for ``place_order`` (NFR-3 cross-language contract).

    Mirrors operator-console's zod ``place_stock_order`` input 1:1 (Q6=A). The
    daemon resolves ``notional`` (a $ amount, market+day only per FR-7) to whole
    shares before risk sizing; ``take_profit``/``stop_loss`` become the bracket
    legs. Validated at the channel boundary (SECURITY-13). ``extra="forbid"`` so a
    console-side typo fails fast instead of being silently dropped.
    """

    model_config = {"extra": "forbid"}

    symbol: str
    side: Literal["buy", "sell"]
    qty: float | None = None
    notional: float | None = None
    order_type: Literal["market", "limit", "stop", "stop_limit", "trailing_stop"] = "market"
    time_in_force: Literal["day", "gtc", "ioc", "fok", "opg", "cls"] = "day"
    limit_price: float | None = None
    stop_price: float | None = None
    trail_price: float | None = None
    trail_percent: float | None = None
    extended_hours: bool = False
    client_order_id: str | None = None
    order_class: Literal["simple", "bracket", "oco", "oto"] = "simple"
    take_profit: float | None = None
    stop_loss: float | None = None
    force: bool = False

EventKind = Literal[
    "outcome", "fill", "decision", "pending", "agent_question", "lifecycle", "reconcile"
]
InterventionKind = Literal["trade", "lifecycle", "note", "directive", "approval", "lock"]


def _new_id() -> str:
    return uuid.uuid4().hex


class SteeringCommand(BaseModel):
    """E7 -- one confirmed operator command appended to ``steering/commands.jsonl``.

    Written by the operator tool (Unit B) AFTER human confirmation; the daemon
    only ever executes records with ``confirmed=True`` and a valid ``token``.
    """

    id: str = Field(default_factory=_new_id)  # outcome-correlation + idempotency key
    ts: datetime = Field(default_factory=datetime.now)
    verb: SteeringVerb
    args: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False  # daemon rejects anything not explicitly True (fail-closed)
    token: str = ""  # operator auth token; validated then dropped from any echo
    source: Literal["human"] = "human"

    def redacted(self) -> dict[str, Any]:
        """Serializable view with the token stripped (for events/logs, SECURITY-03)."""
        data = self.model_dump(mode="json")
        data["token"] = ""
        return data


class SteeringEvent(BaseModel):
    """E8 -- one daemon->operator event in ``steering/events.jsonl``."""

    id: str = Field(default_factory=_new_id)
    corr_id: str | None = None  # the SteeringCommand.id this is an outcome for, if any
    ts: datetime = Field(default_factory=datetime.now)
    kind: EventKind
    payload: dict[str, Any] = Field(default_factory=dict)  # no secrets (SECURITY-03)


class AgentQuestion(BaseModel):
    """E9 -- a question the agent leaves for the human (FR-7).

    Append-only in ``workspace/agent_questions.jsonl`` (writer = agent). The
    answer/status live in a SEPARATE daemon-written file and are joined on read
    (never an in-place rewrite of this file -- /critic #7).
    """

    id: str = Field(default_factory=_new_id)
    ts: datetime = Field(default_factory=datetime.now)
    symbol: str | None = None
    text: str = ""


class AgentAnswer(BaseModel):
    """Daemon-written answer to an AgentQuestion (join key = ``question_id``)."""

    question_id: str
    ts: datetime = Field(default_factory=datetime.now)
    text: str = ""


class InterventionRecord(BaseModel):
    """E2 -- append-only audit log of every human intervention (SECURITY-13)."""

    ts: datetime = Field(default_factory=datetime.now)
    kind: InterventionKind
    raw: str = ""  # operator's original input (NL or reduced command)
    command: str = ""  # parsed verb
    args: dict[str, Any] = Field(default_factory=dict)
    outcome: str = ""  # executed/no_order/rejected/skipped/error/applied/cancelled
    detail: str = ""  # human-readable result (fills/prices/order id or reason)
    rationale: str = ""  # reserved; populated only by /reject <id> <reason> in v1


class Directive(BaseModel):
    """E6 -- a standing instruction surfaced into every agent turn prompt."""

    id: str = Field(default_factory=_new_id)
    ts: datetime = Field(default_factory=datetime.now)
    text: str = ""
    active: bool = True


# --------------------------------------------------------------------------- #
# E3/E4/E5 -- run state, human-lock state machine, pending approvals
# --------------------------------------------------------------------------- #
class RunState(BaseModel):
    """E3 -- daemon lifecycle flags. ET-date scoped persistence (BR-3.3): a
    same-day restart restores pause/halt; a new trading day auto-resets to running."""

    paused: bool = False
    entries_halted: bool = False
    et_date: str = ""  # ISO ET date this state belongs to; "" = unscoped/fresh


LockStatus = Literal["locked", "denied"]


class LockState(BaseModel):
    """E4 -- per-symbol human lock. ``reject_count`` 0->1->2; denied at 2."""

    status: LockStatus = "locked"
    reject_count: int = 0
    et_date: str = ""


class PendingApproval(BaseModel):
    """E5 -- an agent discretionary decision parked for human approval.

    Stores the FULL journal ``Decision`` (not a lossy mirror) so an approved
    pending executes with the agent's real confidence (sizing!) and valid_until
    (expiry) intact (critic #7)."""

    id: int  # day-monotonic; /approve <id>
    decision: Decision
    created_ts: datetime = Field(default_factory=datetime.now)
    status: Literal["pending", "approved", "rejected"] = "pending"
    reason: str = ""
    et_date: str = ""

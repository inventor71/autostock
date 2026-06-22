"""Pydantic models for F88 long-horizon triggers.

Design notes (see ``aidlc-docs/tracks/F88/inception/application-design``):

* ``TriggerSpec`` is the canonical, machine-round-trippable description the agent
  submits via MCP ``trigger.register``. It is serialized to ``spec.json`` (the
  authoritative copy — PBT-02 round-trip target); a human-readable ``trigger.md``
  is rendered from it as a *view* and never parsed back.
* The predicate body (``should_fire(ctx) -> {"fire": bool, "why": str}``) lives in a
  separate ``predicate.py`` file — never inline in the spec — so the untrusted code
  and the trusted metadata never share a parser.
* ``Verdict`` is the predicate's return / stdout contract; ``fire`` is coerced to a
  strict bool and ``why`` is truncated (never rejected) so a chatty predicate can't
  blow the wake-prompt budget.
* ``SourceRef`` only admits the catalogue the daemon can actually broker (critic#2):
  ``signal`` (resolved by ``SignalCollector``) and ``webfetch`` (an allow-listed URL
  the daemon GETs with ``httpx``). General ``websearch`` needs a search API and is a
  follow-up — it is intentionally NOT a valid kind here.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Data-source catalogue the BrokeredFetcher can resolve (FR-4, R1 + critic#2). A
# ``signal`` name must be one the SignalCollector knows; ``websearch`` is omitted
# on purpose (no search API in the first cut).
SIGNAL_NAMES: frozenset[str] = frozenset(
    {"macro", "movers", "earnings", "holdings", "sentiment"}
)

TriggerCadence = Literal["hourly", "daily"]  # hourly floor (R4)

# id = lowercase kebab/alnum slug, 1..64 chars (filesystem-safe, no traversal).
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_WHY_MAX = 500          # Verdict.why hard cap (chars)
_THESIS_MAX = 2000      # spec.thesis hard cap (chars)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourceRef(BaseModel):
    """One declared data source the daemon brokers into ``ctx`` before evaluation.

    ``signal`` → ``SignalCollector`` (name must be in :data:`SIGNAL_NAMES`);
    ``webfetch`` → daemon ``httpx`` GET of ``url`` (the allow-list of permitted
    domains is enforced by the fetcher/config at fetch time, not here — this model
    only validates shape). ``key`` is the stable name under which the result is
    placed in ``ctx`` (defaults to the signal name / a slug of the url host).
    """

    model_config = {"extra": "forbid"}

    kind: Literal["signal", "webfetch"]
    name: str | None = None          # signal: catalogue name
    url: str | None = None           # webfetch: absolute http(s) URL
    params: dict[str, Any] = Field(default_factory=dict)
    key: str | None = None           # ctx key override

    @model_validator(mode="after")
    def _shape(self) -> "SourceRef":
        if self.kind == "signal":
            if not self.name or self.name not in SIGNAL_NAMES:
                raise ValueError(
                    f"signal source requires name in {sorted(SIGNAL_NAMES)}, got {self.name!r}"
                )
            if self.url is not None:
                raise ValueError("signal source must not set url")
        elif self.kind == "webfetch":
            if not self.url or not re.match(r"^https?://", self.url):
                raise ValueError("webfetch source requires an absolute http(s) url")
            if self.name is not None:
                raise ValueError("webfetch source must not set name")
        return self

    def ctx_key(self) -> str:
        """Stable key this source occupies in the brokered ``ctx`` dict."""
        if self.key:
            return self.key
        if self.kind == "signal":
            return self.name or "signal"
        # webfetch: host without scheme/path, ':'/'/' → '_'
        host = re.sub(r"^https?://", "", self.url or "").split("/", 1)[0]
        return "fetch_" + re.sub(r"[^a-z0-9]+", "_", host.lower()).strip("_")


class Verdict(BaseModel):
    """The predicate's decision. ``fire`` strict-coerced; ``why`` truncated."""

    model_config = {"extra": "ignore"}

    fire: bool
    why: str = ""

    @field_validator("fire", mode="before")
    @classmethod
    def _strict_bool(cls, v: Any) -> bool:
        # Accept only real booleans (not "true"/1/[]) so a malformed predicate
        # return is treated as a parse error upstream (fail-closed), not a truthy fire.
        if isinstance(v, bool):
            return v
        raise ValueError("verdict 'fire' must be a JSON boolean")

    @field_validator("why")
    @classmethod
    def _cap(cls, v: str) -> str:
        v = v.strip()
        return v if len(v) <= _WHY_MAX else v[: _WHY_MAX - 1] + "…"


class TriggerSpec(BaseModel):
    """Canonical, round-trippable description of a registered trigger (FR-1/FR-3)."""

    model_config = {"extra": "forbid"}

    id: str
    thesis: str
    cadence: TriggerCadence
    expires: datetime                                  # TTL, required (FR-9)
    sources: list[SourceRef] = Field(default_factory=list)
    primary_symbol: str | None = None                  # WakeEvent.symbol (else "MACRO")
    entry_inducing: bool = True                         # default gated under entries_halted
    created: datetime = Field(default_factory=_utcnow)

    @field_validator("id")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError(
                "trigger id must be a lowercase kebab/alnum slug (1-64 chars), "
                f"got {v!r}"
            )
        return v

    @field_validator("thesis")
    @classmethod
    def _thesis(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("thesis must not be empty")
        if len(v) > _THESIS_MAX:
            raise ValueError(f"thesis exceeds {_THESIS_MAX} chars")
        return v

    @field_validator("primary_symbol")
    @classmethod
    def _sym(cls, v: str | None) -> str | None:
        return v.upper() if v else v

    @field_validator("expires", "created")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        # Normalize to tz-aware UTC so expiry comparisons never raise on naive/aware mix.
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or _utcnow()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now >= self.expires

    def wake_symbol(self) -> str:
        return self.primary_symbol or "MACRO"


class TriggerState(BaseModel):
    """Daemon-managed runtime state (``state.json``) — the agent never writes this."""

    model_config = {"extra": "ignore"}

    last_run: datetime | None = None
    last_verdict: Verdict | None = None
    fired_count: int = 0
    last_fired: datetime | None = None
    consecutive_errors: int = 0
    disabled: bool = False
    disabled_reason: str | None = None


class TriggerSummary(BaseModel):
    """One-line view for ``trigger.list``."""

    id: str
    thesis: str
    cadence: TriggerCadence
    expires: datetime
    disabled: bool
    fired_count: int


class TriggerDetail(BaseModel):
    """Full view for ``trigger.inspect`` (spec + state + predicate source)."""

    spec: TriggerSpec
    state: TriggerState
    predicate_src: str

"""Scenario schema: one frozen situation the agent is graded against.

A scenario bundles (a) what the world looks like — tool fixtures served by the
U1 interception plus the workspace files the agent reads, (b) which turn to
run, and (c) what behavior counts as correct. Real-event replays carry their
provenance in ``origin`` so a regression maps back to the lesson it guards.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

#: Mirrors src/agent/journal.py DecisionAction (kept as literals so the eval
#: schema survives without importing the journal at definition time).
ACTIONS = ("BUY", "SELL", "HOLD", "ADJUST_STOP", "SELL_SHORT", "BUY_TO_COVER")


class Expectation(BaseModel):
    """What a correct turn looks like, checkable from decisions.jsonl alone.

    ``no_churn=True`` means the correct behavior is to do nothing: no new
    decisions, or only HOLD carries (HOLD + stop re-affirms protection and is
    not churn). Otherwise at least one new decision for ``focus_symbol`` must
    use one of ``allowed_actions`` — the author enumerates the set knowing the
    held side (a short cover scenario lists BUY_TO_COVER, etc.)."""

    no_churn: bool = False
    allowed_actions: list[str] = Field(default_factory=list)
    focus_symbol: str | None = None
    note: str = ""

    @field_validator("allowed_actions")
    @classmethod
    def _known_actions(cls, v: list[str]) -> list[str]:
        unknown = [a for a in v if a not in ACTIONS]
        if unknown:
            raise ValueError(f"unknown actions: {unknown}")
        return v

    @field_validator("focus_symbol")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class Scenario(BaseModel):
    id: str
    turn_type: Literal["intraday", "wake", "eod"]
    #: provenance: which lesson / real event this scenario freezes
    origin: str = ""
    description: str = ""

    universe: list[str]
    #: brief text injected into the intraday/wake prompt (the Python-assembled
    #: book the production loop would build)
    brief: str | None = None
    #: wake turns: the trigger reasons
    wake_reasons: list[str] = Field(default_factory=list)
    #: eod turns: pre-assembled outcome lines (production builds these from the
    #: broker; the scenario freezes them)
    eod_outcomes: list[str] | None = None

    #: tool command -> fixture key (symbol or "_") -> final tool output
    tool_fixtures: dict[str, dict[str, Any]] = Field(default_factory=dict)
    #: relative path under the sandbox workspace -> file content
    #: (positions/AAPL.md, lessons.md, regime.md, watchlist.md, ...)
    workspace_files: dict[str, str] = Field(default_factory=dict)
    #: prior decisions.jsonl lines (dicts) seeded as history
    decisions_history: list[dict] = Field(default_factory=list)
    #: held positions for the executor replay: symbol -> {qty, avg_entry_price, side}
    held: dict[str, dict[str, Any]] = Field(default_factory=dict)
    #: replay prices for RiskManager/executor: symbol -> last price
    prices: dict[str, float] = Field(default_factory=dict)

    expectation: Expectation
    #: rubric id under evals/rubrics/ (defaults to the turn type)
    rubric: str | None = None

    @field_validator("universe")
    @classmethod
    def _non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("universe must not be empty")
        return [s.upper() for s in v]


def load_scenario(path: str | Path) -> Scenario:
    return Scenario.model_validate_json(Path(path).read_text(encoding="utf-8"))


def save_scenario(scenario: Scenario, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(scenario.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

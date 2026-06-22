"""U1 — WakeKind taxonomy now admits agent_trigger (F88 integration point)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.agent.intraday.records import WakeEvent


def test_agent_trigger_wake_event_constructs():
    ev = WakeEvent(
        kind="agent_trigger",
        symbol="MACRO",
        reason="vix>25 and spy 5d -4%",
        payload={"trigger_id": "vix-spike", "thesis": "regime shift"},
        entry_inducing=True,
    )
    assert ev.kind == "agent_trigger"
    assert ev.symbol == "MACRO"
    assert ev.payload["trigger_id"] == "vix-spike"


def test_unknown_wake_kind_still_rejected():
    with pytest.raises(ValidationError):
        WakeEvent(kind="not_a_kind", symbol="X", reason="r")

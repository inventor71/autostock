"""U4 — wake_prompt macro branch + macro_triggers_from_events (critic#6)."""

from __future__ import annotations

from src.agent import prompts
from src.agent.intraday.records import WakeEvent


def _agent_trigger(thesis="regime shift", why="vix>25"):
    return WakeEvent(kind="agent_trigger", symbol="MACRO", reason=why,
                     payload={"trigger_id": "t", "thesis": thesis}, entry_inducing=True)


def test_extract_macro_from_events():
    events = [
        _agent_trigger("semis rolling over", "capex cut x2"),
        WakeEvent(kind="new_fill", symbol="AAPL", reason="buy 10 AAPL"),
    ]
    macro = prompts.macro_triggers_from_events(events)
    assert macro == [{"thesis": "semis rolling over", "why": "capex cut x2"}]


def test_macro_prompt_relaxes_symbol_constraint():
    macro = [{"thesis": "semis rolling over", "why": "capex cut"}]
    p = prompts.wake_prompt(None, reasons=["capex cut"], macro_triggers=macro)
    assert "MACRO TRIGGER" in p
    assert "semis rolling over" in p
    # the symbol-only constraint must NOT be present for a macro wake
    assert "Check ONLY the specific symbol" not in p
    assert "across your book" in p


def test_non_macro_prompt_keeps_symbol_constraint():
    p = prompts.wake_prompt(None, reasons=["buy 10 AAPL"])
    assert "Check ONLY the specific symbol" in p
    assert "MACRO TRIGGER" not in p


def test_macro_prompt_handles_missing_thesis():
    macro = prompts.macro_triggers_from_events([
        WakeEvent(kind="agent_trigger", symbol="MACRO", reason="cond", payload={"trigger_id": "t"}),
    ])
    p = prompts.wake_prompt(None, macro_triggers=macro)
    assert "(no thesis recorded)" in p

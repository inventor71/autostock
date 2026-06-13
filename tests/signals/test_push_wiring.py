"""The signal brief must reach EVERY research-prompt path (F61, FR-5 push).

Regression guard for the multi-agent gap: in parallel mode the discovery
sub-agent and the synthesis prompt must also receive the brief, not just the
single-session path.
"""

from __future__ import annotations

from src.agent import prompts

_BRIEF = "## Market signal brief\n  - AVGO -15.0% → NVDA, AMD"
_UNI = ["AVGO", "NVDA", "AMD"]


def test_morning_prompt_prepends_brief():
    assert _BRIEF in prompts.morning_research_prompt(_UNI, [], signal_brief=_BRIEF)
    assert _BRIEF not in prompts.morning_research_prompt(_UNI, [])


def test_multi_initial_prompt_prepends_brief():
    out = prompts.multi_research_initial_prompt(_UNI, [], None, [], 2, signal_brief=_BRIEF)
    assert _BRIEF in out
    assert _BRIEF not in prompts.multi_research_initial_prompt(_UNI, [], None, [], 2)


def test_sub_agent_prompt_prepends_brief():
    out = prompts.sub_agent_prompt("Discovery task", _UNI, None, signal_brief=_BRIEF)
    assert _BRIEF in out
    assert _BRIEF not in prompts.sub_agent_prompt("Discovery task", _UNI, None)


def test_parallel_synthesis_prompt_prepends_brief():
    out = prompts.parallel_synthesis_prompt(["report A"], signal_brief=_BRIEF)
    assert _BRIEF in out
    assert _BRIEF not in prompts.parallel_synthesis_prompt(["report A"])


# F78: the IPO/catalyst Regime nudge (FR-5) must reach EVERY primary research
# prompt — not just the single-session path. The daemon runs multi-agent by
# default, so a nudge only in morning_research_prompt would be inert in prod.
def test_ipo_catalyst_nudge_on_all_primary_research_prompts():
    morning = prompts.morning_research_prompt(_UNI, [])
    multi = prompts.multi_research_initial_prompt(_UNI, [], None, [], 2)
    for out in (morning, multi):
        assert "ipo_calendar" in out
        assert "catalyst" in out.lower()
        # the awareness guard (no trading outside the universe) travels with it
        assert "universe" in out.lower()

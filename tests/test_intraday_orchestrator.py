"""Step 9 — orchestrator run_intraday(brief)/run_wake + prompts wiring."""

from __future__ import annotations

from types import SimpleNamespace

from src.agent.intraday.records import WakeEvent
from src.agent.journal import Journal
from src.agent.orchestrator import AgentTradingLoop
from src.agent.prompts import intraday_prompt, wake_prompt


class _StubSession:
    def __init__(self, journal):
        self.journal = journal
        self.model = "stub"
        self.prompts: list[str] = []
        self.timeouts: list = []

    def run_turn(self, prompt, model=None, timeout=None):
        self.prompts.append(prompt)
        self.timeouts.append(timeout)
        return SimpleNamespace(raw={"ok": 1})


def _orch(tmp_path):
    sess = _StubSession(Journal(root=tmp_path / "ws"))
    return AgentTradingLoop(session=sess, universe=["AAPL"]), sess


# ---- prompt rendering ------------------------------------------------------ #
def test_intraday_prompt_brief_replaces_quotes():
    p = intraday_prompt(brief="MYBRIEF-BLOCK")
    assert "MYBRIEF-BLOCK" in p and "Positions / watchlist to check" not in p


def test_intraday_prompt_legacy_without_brief():
    p = intraday_prompt(held=["AAPL"])
    assert "Positions / watchlist to check: AAPL" in p


def test_wake_prompt_lists_reasons_and_brief():
    p = wake_prompt("BRIEF-X", ["META filled 50sh", "RTX close_above 182 met"])
    assert "Event-driven wake turn" in p and "META filled 50sh" in p and "BRIEF-X" in p


# ---- orchestrator ---------------------------------------------------------- #
def test_run_intraday_injects_brief(tmp_path):
    orch, sess = _orch(tmp_path)
    orch.run_intraday(brief="BRIEF-123")
    assert "BRIEF-123" in sess.prompts[-1]


def test_run_intraday_legacy_uses_held(tmp_path):
    orch, sess = _orch(tmp_path)
    orch.run_intraday()  # no brief -> legacy held path (journal -> none)
    assert "Positions / watchlist to check: none" in sess.prompts[-1]


def test_run_wake_builds_prompt_and_passes_timeout(tmp_path):
    orch, sess = _orch(tmp_path)
    ev = WakeEvent(kind="new_fill", symbol="META", reason="META filled 50sh")
    orch.run_wake("BRIEF-Z", [ev], timeout=120.0)
    assert "META filled 50sh" in sess.prompts[-1] and "BRIEF-Z" in sess.prompts[-1]
    assert sess.timeouts[-1] == 120.0

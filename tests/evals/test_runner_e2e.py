"""End-to-end pipeline with a fake claude runner (zero tokens, zero network).

The fake runner stands in for the `claude` CLI process: it receives the fully
assembled prompt on stdin and "acts" by appending decision lines to the
sandbox journal — exactly what the real agent does via its Write tool. This
proves the wiring the framework's purpose depends on:

- the prompt the subject sees carries the constitution + the PINNED guidance
  version (acceptance criterion 7 — without this the FR-7 matrix is a no-op),
- decisions written during the turn are extracted and stamped with that
  version, and
- the run leaves the production workspace untouched.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.agent.constitution import AGENT_CONSTITUTION

from src.evals.runner import evaluate_scenario
from src.evals.scenario import Expectation, Scenario


def _ok_payload(text="reviewed."):
    return json.dumps({"type": "result", "result": text,
                       "is_error": False, "session_id": "eval-sid"})


class _ActingRunner:
    """Fake `claude` process: records the prompt, writes decisions like the
    agent would, returns a success payload."""

    def __init__(self, decisions: list[dict]):
        self.decisions = decisions
        self.calls: list[dict] = []

    def __call__(self, cmd, *, input, cwd, timeout, env=None):
        self.calls.append({"cmd": cmd, "input": input, "cwd": cwd, "env": env})
        if self.decisions:
            with open(Path(cwd) / "decisions.jsonl", "a", encoding="utf-8") as f:
                for d in self.decisions:
                    f.write(json.dumps(d) + "\n")
        return SimpleNamespace(returncode=0, stdout=_ok_payload(), stderr="")


def _scenario(**kw) -> Scenario:
    base = dict(
        id="e2e", turn_type="intraday", origin="test",
        universe=["AAPL"],
        brief="AAPL 305.0 — stop 300 resting; fresh adverse headline.",
        tool_fixtures={"quote": {"AAPL": {"price": 305.0}}},
        workspace_files={"positions/AAPL.md": "# AAPL\nstop 300 / target 350\n"},
        held={"AAPL": {"qty": 10, "avg_entry_price": 309.0, "side": "long"}},
        prices={"AAPL": 305.0},
        expectation=Expectation(allowed_actions=["SELL", "ADJUST_STOP"],
                                focus_symbol="AAPL"),
    )
    base.update(kw)
    return Scenario(**base)


GUIDANCE_V2 = {
    "current_version": "g2",
    "versions": {
        "seed": {"version": "seed", "evolved_section": "seed text", "status": "active"},
        "g2": {"version": "g2", "parent_version": "seed",
               "evolved_section": "EVAL-MARKER-G2: prefer pre-empting armed exits.",
               "status": "active"},
    },
}


class TestEndToEnd:
    def test_pinned_guidance_reaches_prompt_and_stamp(self):
        """Acceptance 7: the pinned version's text is in the subject prompt AND
        stamped onto the emitted decisions."""
        runner = _ActingRunner([{"symbol": "AAPL", "action": "SELL",
                                 "sell_pct": 1.0, "reason": "armed exit fired"}])
        report = evaluate_scenario(
            _scenario(), guidance_history=GUIDANCE_V2, guidance_label="g2",
            runner=runner,
        )
        prompt = runner.calls[0]["input"]
        assert AGENT_CONSTITUTION.splitlines()[0] in prompt
        assert "EVAL-MARKER-G2" in prompt          # guidance version injected
        assert "adverse headline" in prompt         # scenario brief included
        assert report["stamped_versions"] == ["g2"]
        assert report["tier1"]["behavior"]["matched"] is True
        assert report["tier1"]["hard"]["extraction_ok"] is True

    def test_seed_guidance_default(self):
        runner = _ActingRunner([])
        report = evaluate_scenario(_scenario(), runner=runner)
        assert "EVOLVABLE GUIDANCE" in runner.calls[0]["input"]
        assert report["stamped_versions"] == []  # no decisions -> no stamps

    def test_no_churn_scenario_pass_and_fail(self):
        quiet = _scenario(expectation=Expectation(no_churn=True))
        ok = evaluate_scenario(quiet, runner=_ActingRunner([]))
        assert ok["tier1"]["behavior"]["matched"] is True

        churn = evaluate_scenario(
            quiet, runner=_ActingRunner(
                [{"symbol": "AAPL", "action": "BUY", "stop": 290.0,
                  "reason": "noise chase"}]))
        assert churn["tier1"]["behavior"]["matched"] is False
        # The churn decision still went through the REAL executor gate.
        assert churn["tier1"]["executor_replay"][0]["status"] in (
            "executed", "no_order")

    def test_eod_turn_uses_frozen_outcomes(self):
        runner = _ActingRunner([])
        scenario = _scenario(
            turn_type="eod", brief=None,
            eod_outcomes=["AAPL SELL (stop 300) now 305.00 -> flat/closed"],
            expectation=Expectation(no_churn=True),
        )
        evaluate_scenario(scenario, runner=runner)
        prompt = runner.calls[0]["input"]
        assert "flat/closed" in prompt
        # EOD is not a guidance-bearing turn in production; same here.
        assert "EVOLVABLE GUIDANCE" not in prompt

    def test_fixture_env_restored_and_workspace_untouched(self, monkeypatch):
        import os

        from src.agent.tools.fixtures import FIXTURE_ENV
        monkeypatch.delenv(FIXTURE_ENV, raising=False)
        report = evaluate_scenario(_scenario(), runner=_ActingRunner([]))
        assert FIXTURE_ENV not in os.environ
        assert report["sandbox"] is None  # cleaned up
        # The fake runner ran with cwd inside a temp sandbox, never the repo.
        # (workspace/ untouched is asserted by the cwd check in the runner.)

    def test_one_shot_session_no_resume(self):
        runner = _ActingRunner([])
        evaluate_scenario(_scenario(), runner=runner)
        cmd = runner.calls[0]["cmd"]
        assert "--session-id" in cmd and "--resume" not in cmd

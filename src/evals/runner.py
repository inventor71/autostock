"""One-call pipeline: scenario file -> sandbox -> turn -> artifacts -> grades.

This is the seam the promptfoo provider (and tests) drive. The report is a
plain JSON-able dict so promptfoo asserts and the web viewer can read it
directly."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.agent.journal import Journal

from src.evals.artifacts import collect_artifacts
from src.evals.grading import grade_tier1
from src.evals.sandbox import build_sandbox, run_scenario_turn
from src.evals.scenario import Scenario, load_scenario


def evaluate_scenario(
    scenario: Scenario | str | Path,
    *,
    guidance_history: dict | None = None,
    guidance_label: str = "seed",
    model: str = "sonnet",
    timeout: float | None = None,
    runner=None,
    session_factory=None,
    keep_sandbox: bool = False,
) -> dict[str, Any]:
    if not isinstance(scenario, Scenario):
        scenario = load_scenario(scenario)

    sandbox = build_sandbox(scenario, guidance_history=guidance_history)
    try:
        journal = Journal(sandbox.workspace)
        decisions_before = len(journal.read_decisions())
        raw_before = journal.count_decisions()

        loop, result = run_scenario_turn(
            sandbox, model=model, timeout=timeout,
            runner=runner, session_factory=session_factory,
        )
        artifacts = collect_artifacts(
            sandbox, loop, result,
            decisions_before=decisions_before, raw_lines_before=raw_before,
        )
        tier1 = grade_tier1(scenario, artifacts, journal_root=sandbox.workspace)
        return {
            "scenario_id": scenario.id,
            "turn_type": scenario.turn_type,
            "origin": scenario.origin,
            "guidance_version": guidance_label,
            "stamped_versions": sorted({d.prompt_version for d in artifacts.new_decisions}),
            "response_text": artifacts.response_text,
            "new_decisions": [d.model_dump(mode="json") for d in artifacts.new_decisions],
            "thesis_changed": sorted(artifacts.thesis_changes),
            "tier1": tier1,
            "sandbox": str(sandbox.root) if keep_sandbox else None,
        }
    finally:
        if not keep_sandbox:
            sandbox.cleanup()

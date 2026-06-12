"""Turn artifact extraction: what did the agent actually do.

The agent's real output is its journal writes, not its prose. Artifacts are
the decision-line diff (already stamped with the guidance ``prompt_version``
by the orchestrator), the thesis-file diffs, and the response text — plus the
raw/parsed line-count delta so grading can prove no decision line was lost to
a malformed write (extraction integrity)."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.agent.journal import Decision, Journal

from src.evals.sandbox import Sandbox


@dataclass
class TurnArtifacts:
    response_text: str
    new_decisions: list[Decision]
    #: positions/<file>.md -> (before, after); only files that changed/appeared
    thesis_changes: dict[str, tuple[str, str]]
    #: raw decisions.jsonl line delta vs parsed-decision delta (must match)
    raw_line_delta: int
    parsed_delta: int

    @property
    def extraction_ok(self) -> bool:
        return self.raw_line_delta == self.parsed_delta


def collect_artifacts(
    sandbox: Sandbox,
    loop,
    result,
    *,
    decisions_before: int,
    raw_lines_before: int,
) -> TurnArtifacts:
    journal: Journal = loop.journal
    new = list(loop.last_new_decisions)

    positions = sandbox.workspace / "positions"
    changes: dict[str, tuple[str, str]] = {}
    if positions.is_dir():
        for p in sorted(positions.glob("*.md")):
            after = p.read_text(encoding="utf-8")
            before = sandbox.thesis_before.get(p.name, "")
            if after != before:
                changes[p.name] = (before, after)

    return TurnArtifacts(
        response_text=getattr(result, "result", "") or "",
        new_decisions=new,
        thesis_changes=changes,
        raw_line_delta=journal.count_decisions() - raw_lines_before,
        parsed_delta=len(journal.read_decisions()) - decisions_before,
    )

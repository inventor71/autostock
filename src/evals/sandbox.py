"""Sandbox construction and turn execution for one scenario run.

The sandbox is a throwaway workspace the production stack runs against
unmodified: ``AgentTradingLoop`` assembles the prompt (constitution + guidance
+ turn core) exactly as live turns do, the agent's tool subprocesses answer
from the scenario fixture (U1 interception), and journal writes land in the
temp directory. Isolation is structural — nothing here references the real
``workspace/`` or a live broker.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from src.agent.tools.fixtures import FIXTURE_ENV
from src.evals.scenario import Scenario
from src.core.markettime import ET

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE = _REPO_ROOT / "evals" / "workspace_template"


@dataclass
class Sandbox:
    root: Path  # the temp dir; workspace and fixtures live inside
    workspace: Path
    fixture_dir: Path
    scenario: Scenario
    #: positions/*.md contents at build time, for thesis-diff extraction
    thesis_before: dict[str, str] = field(default_factory=dict)

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def build_sandbox(
    scenario: Scenario,
    *,
    guidance_history: dict | None = None,
    template_dir: str | Path = DEFAULT_TEMPLATE,
    manual: str | None = None,
) -> Sandbox:
    """Materialize the scenario into an isolated workspace + fixture dir.

    ``guidance_history`` is the full guidance/history.json payload to pin a
    specific F64 guidance version (the FR-7 matrix axis); None runs the seed
    version, same as a fresh live workspace.
    """
    root = Path(tempfile.mkdtemp(prefix=f"autostock-eval-{scenario.id}-"))
    ws = root / "workspace"
    ws.mkdir()

    template_dir = Path(template_dir)
    claude_md = template_dir / "CLAUDE.md"
    if not claude_md.exists():
        raise FileNotFoundError(
            f"workspace template missing: {claude_md} — the agent's behavioral "
            "contract must be pinned in git, not read from the live workspace"
        )
    shutil.copy(claude_md, ws / "CLAUDE.md")
    if manual is not None:
        (ws / "CLAUDE.md").write_text(manual, encoding="utf-8")

    for rel, content in scenario.workspace_files.items():
        target = ws / rel
        if not target.resolve().is_relative_to(ws.resolve()):
            raise ValueError(f"workspace_files escapes the sandbox: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    if scenario.decisions_history:
        lines = [json.dumps(d, default=str) for d in scenario.decisions_history]
        (ws / "decisions.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if guidance_history is not None:
        gdir = ws / "guidance"
        gdir.mkdir()
        (gdir / "history.json").write_text(
            json.dumps(guidance_history, indent=2), encoding="utf-8")

    fixture_dir = root / "fixtures"
    fixture_dir.mkdir()
    for cmd, by_key in scenario.tool_fixtures.items():
        (fixture_dir / f"{cmd}.json").write_text(
            json.dumps(by_key, indent=2, default=str), encoding="utf-8")

    thesis_before = {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted((ws / "positions").glob("*.md"))
    } if (ws / "positions").is_dir() else {}

    return Sandbox(root=root, workspace=ws, fixture_dir=fixture_dir,
                   scenario=scenario, thesis_before=thesis_before)


@contextmanager
def _fixture_env(sandbox: Sandbox):
    """Export the fixture dir for the duration of the turn. The agent invokes
    tools as subprocesses; AgentSession copies os.environ into the agent env,
    so a process-level variable is the only channel that survives the hops."""
    prev = os.environ.get(FIXTURE_ENV)
    previous_root = os.environ.get("AGENT_JOURNAL_ROOT")
    os.environ[FIXTURE_ENV] = str(sandbox.fixture_dir)
    os.environ["AGENT_JOURNAL_ROOT"] = str(sandbox.workspace)
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop(FIXTURE_ENV, None)
        else:
            os.environ[FIXTURE_ENV] = prev
        if previous_root is None:
            os.environ.pop("AGENT_JOURNAL_ROOT", None)
        else:
            os.environ["AGENT_JOURNAL_ROOT"] = previous_root


def run_scenario_turn(
    sandbox: Sandbox,
    *,
    model: str = "claude-sonnet-5-5",
    timeout: float | None = None,
    runner=None,
    session_factory=None,
    research_mode: str = "single",
    n_agents: int = 3,
    effort: str = "high",
    provider: str = "claude_code",
    prompt_module=None,
    observer=None,
    api_client=None,
):
    """Run the scenario's turn through the production loop. Returns the
    ``AgentTradingLoop`` (whose ``last_new_decisions`` carry the stamped
    output) and the raw ``AgentTurnResult``."""
    from src.agent.orchestrator import AgentTradingLoop
    from src.agent.session import AgentSession

    scenario = sandbox.scenario
    if research_mode not in ("single", "sequential", "parallel"):
        raise ValueError(f"unknown research mode: {research_mode}")
    if not 2 <= n_agents <= 5:
        raise ValueError("n_agents must be between 2 and 5 for comparison")
    if session_factory is not None:
        session = session_factory(sandbox)
    elif provider == "openai":
        from config.config import get_settings
        from src.agent.openai_session import OpenAIAgentSession
        session = OpenAIAgentSession(
            workspace=sandbox.workspace, model=model, effort=effort,
            api_key=get_settings().openai_api_key, client=api_client, observer=observer,
            one_shot=scenario.turn_type != "research", allow_web=False,
            session_date=scenario.as_of.astimezone(ET).date() if scenario.as_of else None,
            **({"timeout": timeout} if timeout else {}),
        )
    elif provider == "claude_code":
        session = AgentSession(
            workspace=sandbox.workspace,
            model=model,
            effort=effort,
            session_date=scenario.as_of.astimezone(ET).date() if scenario.as_of else None,
            # Sequential research must retain context BETWEEN its rounds. Its
            # state lives in this unique sandbox, never a production session.
            one_shot=scenario.turn_type != "research",
            runner=runner,
            **({"timeout": timeout} if timeout else {}),
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")
    loop = AgentTradingLoop(
        session=session,
        universe=scenario.universe,
        portfolio_provider=lambda: SimpleNamespace(positions=scenario.held),
        research_model=model,
        research_effort=effort,
        research_timeout=timeout,
        multi_agent_enabled=research_mode != "single",
        multi_agent_mode=research_mode if research_mode != "single" else "sequential",
        multi_agent_n=n_agents,
        signal_brief_provider=lambda: (
            f"Information cutoff: {scenario.as_of.isoformat()}. Evaluate at this time; "
            "ignore later events, including anything recalled from training.\n" + (scenario.brief or "")
        ) if scenario.as_of else scenario.brief,
        shorting_enabled=scenario.shorting_enabled,
        # reflection drives lesson recall via outcome collection (price
        # provider = network). The v1 turn types never consume recalled
        # lessons, so disable it outright — structural zero-network guarantee.
        reflection_enabled=False,
        # F85: run the turn at the scenario's aggressiveness so behavior grading
        # can compare conservative vs aggressive posture.
        aggressiveness=scenario.aggressiveness,
        prompt_module=prompt_module,
        as_of=scenario.as_of,
    )

    with _fixture_env(sandbox):
        if scenario.turn_type == "research":
            result = loop.run_morning_research()
        elif scenario.turn_type == "intraday":
            result = loop.run_intraday(scenario.brief)
        elif scenario.turn_type == "wake":
            events = [SimpleNamespace(reason=r) for r in scenario.wake_reasons]
            result = loop.run_wake(scenario.brief, events, timeout=timeout)
        else:  # eod
            result = loop.run_eod_review(outcomes=scenario.eod_outcomes)
    return loop, result

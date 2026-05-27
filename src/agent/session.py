"""Agentic Claude Code session: the PM agent's connection to the LLM.

Wraps the local ``claude`` CLI in headless print mode (``claude -p``) with tools
ENABLED and run inside the agent workspace, so the agent can read/write its
journal, pull market data via ``python -m src.agent.tools``, and research on the
web. Unlike the single-shot ``ClaudeCodeClient`` (tools disabled, throwaway cwd),
this persists a **daily session**: the first turn of the day creates it
(``--session-id``), later turns resume it (``--resume``) for reasoning
continuity, and each new day uses a fresh session id so context never bleeds
across days. The journal (files) is the durable memory; the session is just
within-day continuity.

Subscription auth is inherited from the logged-in CLI (no API key). ``--bare``
is intentionally NOT used: it would force ANTHROPIC_API_KEY auth and skip the
workspace ``CLAUDE.md`` the agent relies on.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from src.agent.journal import Journal

# A deterministic namespace so a given calendar day always maps to one session.
_SESSION_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "autostock-agent")


@dataclass
class AgentTurnResult:
    """Outcome of one agent turn."""

    result: str  # the agent's final text (its journal writes are the real output)
    session_id: str
    resumed: bool
    raw: dict[str, Any] = field(default_factory=dict)


def _default_runner(
    cmd: list[str], *, input: str, cwd: str, timeout: float
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, input=input, capture_output=True, text=True, cwd=cwd, timeout=timeout
    )


class AgentSession:
    """Drives a daily, tool-enabled ``claude -p`` session in the workspace."""

    # Tools the agent may use. File ops are practically bounded to the workspace
    # by cwd; Bash is restricted to the read-only market-data CLI. Web tools let
    # it research. Everything else is denied (no order placement).
    DEFAULT_ALLOWED_TOOLS = (
        "Read",
        "Write",
        "Edit",
        "Glob",
        "Grep",
        "WebSearch",
        "WebFetch",
        "Bash(python -m src.agent.tools:*)",
    )

    def __init__(
        self,
        workspace: str | Path | None = None,
        cli_path: str = "claude",
        model: str = "sonnet",
        allowed_tools: list[str] | None = None,
        permission_mode: str = "dontAsk",
        timeout: float = 600.0,
        session_date: date | None = None,
        runner: Callable[..., subprocess.CompletedProcess] | None = None,
    ):
        self.journal = Journal(workspace)
        self.workspace = self.journal.root
        self.cli_path = cli_path
        self.model = model
        self.allowed_tools = list(allowed_tools or self.DEFAULT_ALLOWED_TOOLS)
        self.permission_mode = permission_mode
        self.timeout = timeout
        self.session_date = session_date or date.today()
        self._runner = runner or _default_runner
        self._started = False

    # ------------------------------------------------------------------ #
    # Session lifecycle
    # ------------------------------------------------------------------ #
    @property
    def session_id(self) -> str:
        """Deterministic per-day session id (same day resumes, new day is fresh)."""
        return str(uuid.uuid5(_SESSION_NAMESPACE, self.session_date.isoformat()))

    def _state_file(self) -> Path:
        return self.workspace / ".sessions" / f"{self.session_date.isoformat()}.json"

    def is_started(self) -> bool:
        """Whether today's session already exists (so the next turn resumes)."""
        return self._started or self._state_file().exists()

    def _mark_started(self) -> None:
        self._started = True
        state_file = self._state_file()
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps({"session_id": self.session_id, "started_at": datetime.now().isoformat()}),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------ #
    # Running a turn
    # ------------------------------------------------------------------ #
    def _build_command(self, system_prompt: str | None, resume: bool) -> list[str]:
        cmd = [
            self.cli_path,
            "-p",
            "--output-format", "json",
            "--model", self.model,
            "--permission-mode", self.permission_mode,
            "--allowedTools", ",".join(self.allowed_tools),
        ]
        if resume:
            cmd += ["--resume", self.session_id]
        else:
            cmd += ["--session-id", self.session_id]
        if system_prompt:
            cmd += ["--append-system-prompt", system_prompt]
        return cmd

    def run_turn(self, prompt: str, system_prompt: str | None = None) -> AgentTurnResult:
        """Run one agent turn. Creates the day's session on the first call and
        resumes it thereafter. The prompt is sent on stdin; the agent's journal
        writes are the meaningful output, the returned text is its summary."""
        self.journal.init()  # ensure workspace + CLAUDE.md exist
        resume = self.is_started()
        cmd = self._build_command(system_prompt, resume)

        logger.info(
            "Agent turn ({}) session={} model={}",
            "resume" if resume else "new",
            self.session_id,
            self.model,
        )
        proc = self._runner(
            cmd, input=prompt, cwd=str(self.workspace), timeout=self.timeout
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"claude CLI exited with {proc.returncode}: {(proc.stderr or '').strip()}"
            )

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Could not parse claude JSON output: {exc}") from exc

        if payload.get("is_error"):
            raise RuntimeError(f"claude returned an error: {payload.get('result')}")

        if not resume:
            self._mark_started()

        return AgentTurnResult(
            result=payload.get("result", ""),
            session_id=payload.get("session_id", self.session_id),
            resumed=resume,
            raw=payload,
        )


def research_prompt(symbols: list[str]) -> str:
    """A minimal morning-research instruction (Phase 2 will enrich turn prompts)."""
    names = ", ".join(symbols)
    return (
        "Morning research turn. Read your CLAUDE.md and journal first.\n"
        f"Focus symbols: {names}.\n"
        "Use the market-data tools (quote/indicators/scoreboard/fundamentals/news) "
        "and web research as needed. For each focus symbol, write or update its "
        "thesis and plan (entry/stop/target) in positions/<SYMBOL>.md, refresh "
        "regime.md and watchlist.md, and append any actionable decisions to "
        "decisions.jsonl following the schema in CLAUDE.md. You are advisory only "
        "— do not attempt to place orders."
    )

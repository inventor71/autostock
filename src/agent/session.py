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
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from src.agent.journal import Journal
from src.core.markettime import ET

# Session day = the US/Eastern calendar date, so the daily session spans the
# whole US trading day (pre-market through close) and rolls at ET midnight
# (off-hours) — even in a long-running process. Using the local date instead
# would split the session mid-session and never roll over while the daemon runs.

# Repo root: src/agent/session.py -> parents[2]. The agent runs with cwd set to
# the workspace, so the repo must be on PYTHONPATH for `python -m src.agent.tools`.
_REPO_ROOT = Path(__file__).resolve().parents[2]

# CLI error fragments that mean the session id can't be used as-is, so we should
# retry with a fresh one (id collided with a stale session, or resume target gone).
_SESSION_ERROR_FRAGMENTS = ("already in use", "no conversation", "not found", "does not exist")


@dataclass
class AgentTurnResult:
    """Outcome of one agent turn."""

    result: str  # the agent's final text (its journal writes are the real output)
    session_id: str
    resumed: bool
    raw: dict[str, Any] = field(default_factory=dict)


def _default_runner(
    cmd: list[str], *, input: str, cwd: str, timeout: float, env: dict | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, input=input, capture_output=True, text=True, cwd=cwd, timeout=timeout, env=env
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
        "Bash(python3 -m src.agent.tools:*)",
    )

    READ_ONLY_TOOLS = (
        "Read", "Glob", "Grep", "WebSearch", "WebFetch",
        "Bash(python -m src.agent.tools:*)",
        "Bash(python3 -m src.agent.tools:*)",
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
        one_shot: bool = False,
    ):
        self.journal = Journal(workspace)
        self.workspace = self.journal.root
        self.cli_path = cli_path
        self.model = model
        self.allowed_tools = list(allowed_tools or self.DEFAULT_ALLOWED_TOOLS)
        self.permission_mode = permission_mode
        self.timeout = timeout
        self._fixed_date = session_date
        self._runner = runner or _default_runner
        self._started = False
        self._one_shot = one_shot

    @classmethod
    def create_sub_agent(
        cls,
        workspace: str | Path,
        model: str = "sonnet",
        timeout: float = 600.0,
        runner: Callable[..., subprocess.CompletedProcess] | None = None,
    ) -> "AgentSession":
        return cls(
            workspace=workspace,
            model=model,
            allowed_tools=list(cls.READ_ONLY_TOOLS),
            timeout=timeout,
            runner=runner,
            one_shot=True,
        )

    # ------------------------------------------------------------------ #
    # Session lifecycle
    # ------------------------------------------------------------------ #
    # A fresh random session id is generated on the first turn of the day and
    # stored in the per-day marker; later turns resume that id. This keeps
    # resume-within-day + fresh-per-day WITHOUT a deterministic id that could
    # collide with a stale session in the CLI store (e.g. after the workspace
    # is cleared while the CLI session persists).
    @property
    def session_date(self) -> date:
        """The session's trading day — live US/Eastern date unless pinned."""
        return self._fixed_date or datetime.now(ET).date()

    def _state_file(self) -> Path:
        return self.workspace / ".sessions" / f"{self.session_date.isoformat()}.json"

    def _read_state(self) -> dict | None:
        sf = self._state_file()
        if sf.exists():
            try:
                return json.loads(sf.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def is_started(self) -> bool:
        """Whether today's session already exists (so the next turn resumes)."""
        return self._read_state() is not None

    @property
    def session_id(self) -> str | None:
        state = self._read_state()
        return state.get("session_id") if state else None

    def _write_state(self, session_id: str) -> None:
        sf = self._state_file()
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(
            json.dumps({"session_id": session_id, "started_at": datetime.now().isoformat()}),
            encoding="utf-8",
        )

    def reset_session(self) -> None:
        """Discard today's stored session so the next turn starts fresh.

        Used on a deliberate launch: the journal carries durable state, while the
        CLI session is just within-run continuity — so a manual restart should
        begin a clean session rather than resume a stale/bloated one. Scheduled
        turns within the run still resume; the ET-date rollover still applies.
        """
        sf = self._state_file()
        if sf.exists():
            sf.unlink()
            logger.info("Cleared session marker {}; next turn starts fresh", sf.name)

    # ------------------------------------------------------------------ #
    # Running a turn
    # ------------------------------------------------------------------ #
    def _build_command(
        self, session_id: str, system_prompt: str | None, resume: bool, model: str | None = None
    ) -> list[str]:
        cmd = [
            self.cli_path,
            "-p",
            "--output-format", "json",
            "--model", model or self.model,
            "--permission-mode", self.permission_mode,
            "--allowedTools", ",".join(self.allowed_tools),
        ]
        cmd += ["--resume", session_id] if resume else ["--session-id", session_id]
        if system_prompt:
            cmd += ["--append-system-prompt", system_prompt]
        return cmd

    def _invoke(
        self, session_id: str, prompt: str, system_prompt: str | None, resume: bool,
        model: str | None = None, timeout: float | None = None,
    ) -> dict:
        cmd = self._build_command(session_id, system_prompt, resume, model)
        # Scrub the operator steering token before it reaches the agent (BR-10.2):
        # dict(os.environ) would otherwise copy the daemon's token to the agent.
        from src.agent.steering.security import scrub_agent_env

        env = scrub_agent_env(dict(os.environ))
        if self._one_shot:
            env["AGENT_JOURNAL_ROOT"] = str(self.workspace)
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(_REPO_ROOT) + (os.pathsep + existing_pp if existing_pp else "")

        # F46: prepend the daemon's own interpreter bin dir to the agent's PATH so
        # `python`/`python3` resolve to the exact same interpreter (venv, has alpaca-py).
        # Without this, the agent's PATH (inherited from the systemd unit) lacks the venv
        # bin dir, so `python3` → system `/usr/bin/python3` (yfinance OK, alpaca missing)
        # → `account` tool fails with BrokerError("alpaca-py not installed").
        bin_dir = os.path.dirname(sys.executable)
        existing_path = env.get("PATH", "")
        env["PATH"] = bin_dir + (os.pathsep + existing_path if existing_path else "")

        proc = self._runner(
            cmd, input=prompt, cwd=str(self.workspace), timeout=timeout or self.timeout, env=env
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
        return payload

    def run_turn(
        self, prompt: str, system_prompt: str | None = None, model: str | None = None,
        timeout: float | None = None,
    ) -> AgentTurnResult:
        """Run one agent turn. Creates the day's session on the first call and
        resumes it thereafter (id stored in the per-day marker). If the stored id
        is unusable (stale/collision), retry once with a fresh session. ``model``
        overrides the session default for this turn (e.g. opus for research). The
        prompt is sent on stdin; the agent's journal writes are the real output."""
        self.journal.init()  # ensure workspace + CLAUDE.md exist
        if self._one_shot:
            session_id = str(uuid.uuid4())
            resume = False
        else:
            state = self._read_state()
            session_id = state.get("session_id") if state else None
            resume = session_id is not None
            if session_id is None:
                session_id = str(uuid.uuid4())

        logger.info(
            "Agent turn ({}) session={} model={}",
            "resume" if resume else "new", session_id, model or self.model,
        )
        try:
            payload = self._invoke(session_id, prompt, system_prompt, resume, model, timeout)
        except RuntimeError as exc:
            if any(frag in str(exc).lower() for frag in _SESSION_ERROR_FRAGMENTS):
                logger.warning("Session id unusable ({}); retrying with a fresh session", exc)
                session_id = str(uuid.uuid4())
                resume = False
                payload = self._invoke(session_id, prompt, system_prompt, resume, model, timeout)
            else:
                raise

        if not self._one_shot and not resume:
            self._write_state(session_id)

        return AgentTurnResult(
            result=payload.get("result", ""),
            session_id=payload.get("session_id", session_id),
            resumed=resume,
            raw=payload,
        )

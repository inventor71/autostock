"""Explicit model/effort/prompt axes; historical prompts use current execution code."""

from __future__ import annotations

import hashlib
import re
import subprocess
import types
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from config.config import ReasoningEffort

ROOT = Path(__file__).resolve().parents[2]


class ResearchProfile(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    provider: Literal["claude_code", "openai"] = "claude_code"
    model: str
    effort: ReasoningEffort = "high"
    prompt_ref: str = "current"


def prompt_snapshot(ref: str) -> tuple[types.ModuleType | None, str | None, dict]:
    """Pin the turn-prompt module and manual, without checking out old risk code.

    Git references are trusted local repository code, not downloadable prompts.
    Runtime controls, guidance, fixture tools and risk gates remain identical.
    """
    paths = ("src/agent/prompts.py", "src/agent/templates/CLAUDE.md")
    if ref == "current":
        blobs = {p: (ROOT / p).read_text() for p in paths}
        resolved = "current"
    elif ref.startswith("baseline:"):
        name = ref.removeprefix("baseline:")
        if not re.fullmatch(r"[a-z0-9-]+", name):
            raise ValueError("Invalid bundled baseline name")
        directory = ROOT / "evals/baselines" / name
        blobs = {paths[0]: (directory / "prompts.py").read_text(),
                 paths[1]: (directory / "CLAUDE.md").read_text()}
        resolved = ref
    else:
        resolved = subprocess.check_output(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=ROOT, text=True).strip()
        blobs = {p: subprocess.check_output(["git", "show", f"{resolved}:{p}"],
                                            cwd=ROOT, text=True) for p in paths}
    metadata = {"ref": resolved, "sha256": {
        p: hashlib.sha256(content.encode()).hexdigest() for p, content in blobs.items()},
        "files": blobs}
    if ref == "current":
        return None, blobs[paths[1]], metadata
    module = types.ModuleType(f"historical_prompts_{resolved}")
    exec(compile(blobs[paths[0]], f"{resolved}:{paths[0]}", "exec"), module.__dict__)
    return module, blobs[paths[1]], metadata

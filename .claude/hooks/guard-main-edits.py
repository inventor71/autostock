#!/usr/bin/env python3
"""PreToolUse guard: block application-code edits on the *main* checkout while a
track is active.

Rationale: CLAUDE.md mandates a blocking "worktree gate" — no application code may
be generated outside a worktree. That rule lived only as prose and depended on the
model's discipline, so edits kept leaking into main. This hook makes the gate a
hard, structural constraint.

Conditional enforcement (user choice 2026-06-04): only blocks when the root Track
Registry has at least one `active` track. With zero active tracks (e.g. initial
setup), main edits pass through.

Always-allowed targets (never blocked):
  - anything under .claude/worktrees/        (you're already in a worktree)
  - aidlc-docs/                              (documentation — the doc layer)
  - .claude/                                 (settings / hooks)
  - .aidlc-rule-details/, .aidlc/, .kiro/, .amazonq/   (workflow rules)
  - any *.md file                            (docs, including CLAUDE.md)
  - paths outside the main checkout entirely

Escape hatch for an intentional main hotfix:
  set AUTOSTOCK_ALLOW_MAIN_EDIT=1 in the environment.

Blocking mechanism: exit code 2 + message on stderr (PreToolUse contract — the
tool call is denied and the message is shown back to Claude).
"""

import json
import os
import sys
from pathlib import Path

# main checkout root = two levels up from .claude/hooks/guard-main-edits.py
MAIN_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = MAIN_ROOT / "aidlc-docs" / "aidlc-state.md"

# path prefixes (relative to MAIN_ROOT) that are always editable on main
ALLOWED_PREFIXES = (
    ".claude/worktrees/",  # actually a worktree, not main
    "aidlc-docs/",
    ".claude/",
    ".aidlc-rule-details/",
    ".aidlc/",
    ".kiro/",
    ".amazonq/",
)


def has_active_track() -> bool:
    """True if the root Track Registry has any row whose Status cell is 'active'."""
    try:
        text = REGISTRY.read_text(encoding="utf-8")
    except OSError:
        # no registry → can't assert a track is active → don't block
        return False
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        # table row: ['', 'ID', 'Title', 'Status', 'Branch', ...]
        if len(cells) < 4:
            continue
        if cells[3].lower().startswith("active"):
            return True
    return False


def main() -> int:
    if os.environ.get("AUTOSTOCK_ALLOW_MAIN_EDIT") == "1":
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # fail-open on malformed input — never wedge the editor

    if payload.get("tool_name") not in ("Edit", "Write", "NotebookEdit"):
        return 0

    tool_input = payload.get("tool_input") or {}
    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw_path:
        return 0

    try:
        target = Path(raw_path).resolve()
    except OSError:
        return 0

    # outside the main checkout → not our concern
    try:
        rel = target.relative_to(MAIN_ROOT).as_posix()
    except ValueError:
        return 0

    # always-allowed targets
    if rel.endswith(".md"):
        return 0
    if any(rel.startswith(p) for p in ALLOWED_PREFIXES):
        return 0

    # at this point: application code (or config) on the main checkout
    if not has_active_track():
        return 0  # no track in flight → allow

    sys.stderr.write(
        "BLOCKED by worktree gate (CLAUDE.md): refusing to edit main-checkout "
        f"application code while a track is active.\n  target: {rel}\n"
        "Do the work in the track's worktree (.claude/worktrees/<id>/) instead — "
        "create/enter it first, then edit there.\n"
        "If this really is an intentional main hotfix outside any track, re-run "
        "with AUTOSTOCK_ALLOW_MAIN_EDIT=1 set in the environment.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())

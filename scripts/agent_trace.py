"""Open and read the PM agent's reasoning trace from a Claude Code session.

The agent runs as a headless ``claude -p`` session (see src/agent/session.py)
whose full step-by-step transcript — the agent's narrated reasoning plus every
tool call/result — is stored by Claude Code as a session JSONL under
``~/.claude/projects/<slug>/<session-id>.jsonl``. The app itself only keeps the
final result + cost (``turns.jsonl``); this script is how you read the *why*.

    python scripts/agent_trace.py                 # latest turn, any type
    python scripts/agent_trace.py intraday        # latest intraday turn
    python scripts/agent_trace.py research        # latest morning research turn
    python scripts/agent_trace.py intraday --n 2  # 2nd-most-recent intraday turn
    python scripts/agent_trace.py --list          # index of all turns today
    python scripts/agent_trace.py eod --date 2026-05-28
    python scripts/agent_trace.py --session <id>  # a specific session id

Note: extended-thinking blocks are stored encrypted (signature only, no
plaintext), so the readable trace is the agent's text + tool calls/results.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SESSIONS_DIR = _REPO_ROOT / "workspace" / ".sessions"
_PROJECTS_DIR = Path.home() / ".claude" / "projects"
_ET = ZoneInfo("US/Eastern")

# Prompt headers (see src/agent/prompts.py) that mark the start of each turn.
_TURN_HEADERS = {
    "Morning research turn": "research",
    "Intraday update turn": "intraday",
    "End-of-day review turn": "eod",
}


def _resolve_session_id(date_str: str | None, session: str | None) -> str:
    if session:
        return session
    if date_str:
        marker = _SESSIONS_DIR / f"{date_str}.json"
        if not marker.exists():
            sys.exit(f"no session marker for {date_str} at {marker}")
        return json.loads(marker.read_text())["session_id"]
    # Default: today's ET trading-day session, else the newest marker.
    today = _SESSIONS_DIR / f"{datetime.now(_ET).date().isoformat()}.json"
    if today.exists():
        return json.loads(today.read_text())["session_id"]
    markers = sorted(_SESSIONS_DIR.glob("*.json"))
    if not markers:
        sys.exit(f"no session markers found under {_SESSIONS_DIR}")
    return json.loads(markers[-1].read_text())["session_id"]


def _find_transcript(session_id: str) -> Path:
    matches = list(_PROJECTS_DIR.glob(f"*/{session_id}.jsonl"))
    if not matches:
        sys.exit(f"no transcript found for session {session_id} under {_PROJECTS_DIR}")
    return matches[0]


def _content_blocks(entry: dict) -> list:
    msg = entry.get("message") or {}
    content = msg.get("content")
    return content if isinstance(content, list) else []


def _prompt_text(entry: dict) -> str | None:
    """The human-prompt string of a turn-boundary user entry, else None.

    Real prompts are stored as a plain string; tool results come back as a list
    of tool_result blocks (skip those — they are not turn boundaries)."""
    msg = entry.get("message") or {}
    content = msg.get("content")
    return content if isinstance(content, str) else None


def _classify(prompt: str) -> str | None:
    for header, kind in _TURN_HEADERS.items():
        if header in prompt:
            return kind
    return None


def _parse_turns(path: Path) -> list[dict]:
    """Split the session transcript into turns at each human-prompt boundary."""
    turns: list[dict] = []
    current: dict | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = entry.get("type")
        if etype == "user":
            prompt = _prompt_text(entry)
            kind = _classify(prompt) if prompt else None
            if kind is not None:
                current = {"type": kind, "ts": entry.get("timestamp"), "blocks": []}
                turns.append(current)
        elif etype == "assistant" and current is not None:
            current["blocks"].extend(_content_blocks(entry))
    return turns


def _short(value, n: int = 160) -> str:
    s = value if isinstance(value, str) else json.dumps(value, default=str)
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n] + "…"


def _tool_arg(inp: dict) -> str:
    for key in ("command", "query", "url", "file_path", "symbol", "pattern"):
        if key in inp:
            return _short(inp[key])
    return _short(inp)


def _counts(turn: dict) -> tuple[int, int, int]:
    texts = tools = thinks = 0
    for b in turn["blocks"]:
        t = b.get("type")
        texts += t == "text"
        tools += t == "tool_use"
        thinks += t == "thinking"
    return texts, tools, thinks


def _fmt_ts(ts: str | None) -> str:
    if not ts:
        return "?"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(_ET)
        return dt.strftime("%Y-%m-%d %H:%M ET")
    except ValueError:
        return ts


def _print_turn(turn: dict) -> None:
    texts, tools, thinks = _counts(turn)
    print(
        f"=== {turn['type'].upper()} turn @ {_fmt_ts(turn['ts'])} "
        f"({texts} text, {tools} tool calls, {thinks} thinking blocks) ==="
    )
    for b in turn["blocks"]:
        t = b.get("type")
        if t == "thinking":
            print("\n🧠 (extended thinking — stored encrypted, not readable)")
        elif t == "text":
            print("\n💬 " + (b.get("text") or "").strip())
        elif t == "tool_use":
            print(f"\n🔧 {b.get('name')}  {_tool_arg(b.get('input') or {})}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Read the PM agent's reasoning trace.")
    ap.add_argument("turn_type", nargs="?", default="any",
                    choices=["any", "research", "intraday", "eod"],
                    help="which turn type to show (default: any = the latest turn)")
    ap.add_argument("--n", type=int, default=1,
                    help="show the Nth-from-last matching turn (default 1 = most recent)")
    ap.add_argument("--date", help="ET trading date of the session (YYYY-MM-DD)")
    ap.add_argument("--session", help="explicit session id (overrides --date)")
    ap.add_argument("--list", action="store_true", help="list all turns, newest last")
    args = ap.parse_args(argv)

    session_id = _resolve_session_id(args.date, args.session)
    path = _find_transcript(session_id)
    turns = _parse_turns(path)
    if not turns:
        sys.exit(f"no turns parsed from {path}")

    if args.list:
        print(f"session {session_id}  ({len(turns)} turns)\n")
        for i, turn in enumerate(turns):
            texts, tools, thinks = _counts(turn)
            print(f"[{i - len(turns)}] {turn['type']:<9} {_fmt_ts(turn['ts']):<20} "
                  f"{tools} tools")
        return 0

    pool = turns if args.turn_type == "any" else [t for t in turns if t["type"] == args.turn_type]
    if not pool:
        sys.exit(f"no '{args.turn_type}' turns in session {session_id}")
    if args.n < 1 or args.n > len(pool):
        sys.exit(f"--n {args.n} out of range (1..{len(pool)} {args.turn_type} turns)")

    _print_turn(pool[-args.n])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

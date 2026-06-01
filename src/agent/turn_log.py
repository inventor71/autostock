"""Per-turn telemetry (turns.jsonl): cost/activity of each agent turn.

This is ephemeral data the CLI returns once and then drops — capture it now or
it's gone. Used to track daily LLM spend and how active the agent is (and later
to compare aggressiveness profiles by activity).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from loguru import logger

_TYPE_PREFIX = {
    "research": "R", "intraday": "I", "wake": "W", "eod": "E", "reconcile": "C",
}
_TYPE_LABEL = {
    "research": "Research", "intraday": "Intraday", "wake": "Wake",
    "eod": "EOD review", "reconcile": "Reconcile",
}
_ID_RE = re.compile(r"^([A-Z])(\d+)$")


def generate_turn_id(path: str | Path, turn_type: str) -> str:
    """Type-prefixed daily-sequential turn ID (e.g. R1, I3, W1)."""
    prefix = _TYPE_PREFIX.get(turn_type, "T")
    today = datetime.now().date().isoformat()
    max_n = 0
    for rec in read_turns(path):
        if str(rec.get("date", "")) != today:
            continue
        tid = rec.get("turn_id", "")
        m = _ID_RE.match(str(tid))
        if m and m.group(1) == prefix:
            max_n = max(max_n, int(m.group(2)))
    return f"{prefix}{max_n + 1}"


def build_turn_summary(turn_type: str, decisions) -> str:
    """Deterministic 1-line summary from the turn's decisions."""
    label = _TYPE_LABEL.get(turn_type, turn_type.capitalize())
    if not decisions:
        return f"{label}: no decisions"
    parts = []
    for d in decisions[:4]:
        sym = getattr(d, "symbol", None) or d.get("symbol", "?") if isinstance(d, dict) else d.symbol
        act = getattr(d, "action", None) or d.get("action", "?") if isinstance(d, dict) else d.action
        conf = getattr(d, "confidence", None) or d.get("confidence") if isinstance(d, dict) else d.confidence
        conf_s = f"({conf:.1f})" if isinstance(conf, (int, float)) else ""
        parts.append(f"{act} {sym}{conf_s}")
    tail = f", +{len(decisions) - 4} more" if len(decisions) > 4 else ""
    return f"{label}: {', '.join(parts)}{tail}"


def record_turn(
    path: str | Path,
    *,
    turn_type: str,
    model: str,
    num_decisions: int,
    raw: dict | None,
    turn_id: str = "",
    summary: str = "",
    error: bool = False,
    started_at: str = "",
) -> dict:
    """Append one turn's telemetry (cost/duration/tokens/decisions) as JSONL."""
    raw = raw or {}
    usage = raw.get("usage") or {}
    rec = {
        "turn_id": turn_id,
        "started_at": started_at,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "date": datetime.now().date().isoformat(),
        "turn_type": turn_type,
        "model": model,
        "num_decisions": num_decisions,
        "cost_usd": raw.get("total_cost_usd"),
        "duration_ms": raw.get("duration_ms"),
        "num_turns": raw.get("num_turns"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "summary": summary,
        "health": "error" if error else "ok",
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    cost = rec["cost_usd"]
    logger.info(
        "Turn telemetry: {} [{}] decisions={} cost={} dur={}ms",
        turn_type, turn_id, num_decisions,
        f"${cost:.4f}" if isinstance(cost, (int, float)) else "n/a",
        rec["duration_ms"],
    )
    return rec


def read_turns(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out

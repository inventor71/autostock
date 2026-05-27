"""Per-turn telemetry (turns.jsonl): cost/activity of each agent turn.

This is ephemeral data the CLI returns once and then drops — capture it now or
it's gone. Used to track daily LLM spend and how active the agent is (and later
to compare aggressiveness profiles by activity).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from loguru import logger


def record_turn(path: str | Path, *, turn_type: str, model: str, num_decisions: int, raw: dict | None) -> dict:
    """Append one turn's telemetry (cost/duration/tokens/decisions) as JSONL."""
    raw = raw or {}
    usage = raw.get("usage") or {}
    rec = {
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
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    cost = rec["cost_usd"]
    logger.info(
        "Turn telemetry: {} decisions={} cost={} dur={}ms",
        turn_type, num_decisions,
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

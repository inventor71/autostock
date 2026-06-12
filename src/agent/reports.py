"""Per-turn multi-agent evaluation reports (agent_reports/<turn_id>.json).

F41: a research turn run in multi-agent mode produces several independent
evaluations — the rounds of a sequential cross-validation (initial / debate)
or the spawned sub-agents of a parallel run — that are then folded into one
synthesis. Those per-agent evaluations were previously transient (the parallel
sub-agent workspaces are deleted; the sequential rounds live only in the daily
journal narrative), so the operator could not inspect them from the timeline.

This module persists them as one JSON file per turn so the TUI turn overlay can
offer a drill-down into each agent/round's full text. It is *capture only* — no
extra LLM calls — and every write is best-effort: a failure here must never
break the trading turn.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from loguru import logger

from src.agent.logs.turn import compute_et_date

EvalStatus = Literal["ok", "error", "timeout"]

_REPORTS_DIRNAME = "agent_reports"


def _safe_key(turn_id: str, ts: str) -> str:
    """File stem for a turn's report: the turn_id, or a filesystem-safe ts."""
    key = (turn_id or "").strip()
    if not key:
        key = (ts or "unknown").replace(":", "-").replace("/", "-").replace(" ", "_")
    return key


def reports_dir(root: str | Path) -> Path:
    return Path(root) / _REPORTS_DIRNAME


def make_eval(
    *,
    index: int,
    label: str,
    role: str,
    text: str,
    status: EvalStatus = "ok",
    error: str | None = None,
) -> dict:
    """One agent/round evaluation. ``text`` is the full evaluation (never truncated)."""
    return {
        "index": index,
        "label": label,
        "role": role,
        "status": status,
        "text": text or "",
        "error": error,
    }


def build_report(
    *,
    turn_id: str,
    ts: str,
    mode: str,
    agents: list[dict],
    synthesis_text: str,
    turn_type: str = "research",
) -> dict:
    """Assemble the per-turn report record from collected evaluations."""
    return {
        "turn_id": turn_id or "",
        "et_date": compute_et_date(ts),
        "ts": ts,
        "turn_type": turn_type,
        "mode": mode,
        "n_agents": len(agents),
        "agents": agents,
        "synthesis": {"text": synthesis_text or ""},
    }


def write_agent_report(root: str | Path, report: dict) -> Path | None:
    """Persist one turn's report as ``agent_reports/<key>.json`` (atomic).

    Best-effort: any failure is logged and swallowed (returns ``None``) so the
    caller's trading turn is never disrupted (NFR-1)."""
    try:
        d = reports_dir(root)
        d.mkdir(parents=True, exist_ok=True)
        key = _safe_key(report.get("turn_id", ""), report.get("ts", ""))
        path = d / f"{key}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        logger.info(
            "Agent report written: {} ({} mode, {} agents)",
            path.name, report.get("mode"), report.get("n_agents"),
        )
        return path
    except Exception as exc:  # noqa: BLE001 — best-effort telemetry
        logger.warning("Agent report write failed (skipping): {}", exc)
        return None


def read_agent_report(root: str | Path, turn_id: str) -> dict | None:
    """Read a turn's report by turn_id, or None if absent/unreadable."""
    key = (turn_id or "").strip()
    if not key:
        return None
    path = reports_dir(root) / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Agent report read failed for {}: {}", key, exc)
        return None


def has_agent_report(root: str | Path, turn_id: str) -> bool:
    key = (turn_id or "").strip()
    if not key:
        return False
    return (reports_dir(root) / f"{key}.json").exists()

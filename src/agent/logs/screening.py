"""Screening capture (F72): persist the research-turn screening funnel.

Two layers per ET trading date under ``workspace/screening/``:

- ``<date>.scan.json`` — deterministic quant snapshot: every ``scoreboard`` run
  rewrites it atomically, so the file always holds the latest full-universe
  scan (error rows included). Written by the tools CLI as a side effect.
- ``<date>.verdicts.jsonl`` — the agent's own per-candidate screening verdicts
  (``entered`` / ``watchlist`` / ``passed`` + reason), appended directly by the
  LLM subprocess exactly like decisions.jsonl.

The operator console reads both files directly (steer_read ``/screening``), so
nothing here is published through the steering snapshot/monitor views. Saving
is a side effect of the scan and must never sink it: every write failure is a
warning, never an exception (NFR-1).
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.agent.journal import DEFAULT_ROOT
from src.agent.logs.turn import compute_et_date
from src.core.jsonl import atomic_write_text

SCREENING_DIR = "screening"


def resolve_root(root: str | Path | None = None) -> Path:
    """Workspace root shared with the daemon.

    The daemon exports its journal root as ``AGENT_JOURNAL_ROOT`` when it
    spawns the agent (same contract as the ``watch`` tool), so a non-default
    workspace does not split writer and reader.
    """
    if root is not None:
        return Path(root)
    return Path(os.environ.get("AGENT_JOURNAL_ROOT") or DEFAULT_ROOT)


def scan_path(root: str | Path, et_date: str) -> Path:
    return Path(root) / SCREENING_DIR / f"{et_date}.scan.json"


def verdicts_path(root: str | Path, et_date: str) -> Path:
    return Path(root) / SCREENING_DIR / f"{et_date}.verdicts.jsonl"


def record_scan(
    rows: list[dict],
    root: str | Path | None = None,
    ts: datetime | None = None,
) -> Path | None:
    """Persist a scoreboard result under its ET trading date.

    The latest run of the day wins (atomic rewrite); ``ts`` records when it
    ran. Returns the written path, or None on any failure.
    """
    try:
        now = ts or datetime.now().astimezone()
        et_date = compute_et_date(now)
        path = scan_path(resolve_root(root), et_date)
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "et_date": et_date,
            "ts": now.isoformat(),
            "count": len(rows),
            "rows": rows,
        }
        atomic_write_text(path, json.dumps(doc, ensure_ascii=False) + "\n")
        return path
    except Exception as exc:
        logger.warning(f"screening scan not saved ({exc}); scan output unaffected")
        return None


def read_scan(root: str | Path, et_date: str) -> dict | None:
    """Latest scan snapshot for the date, or None if absent/corrupt."""
    try:
        return json.loads(scan_path(root, et_date).read_text(encoding="utf-8"))
    except Exception:
        return None


def read_verdicts(root: str | Path, et_date: str) -> list[dict]:
    """Agent verdicts for the date, lenient: corrupt/torn lines are skipped and
    unknown verdict values are kept as-is (the journal is evidence, not schema)."""
    try:
        text = verdicts_path(root, et_date).read_text(encoding="utf-8")
    except Exception:
        return []
    records: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict):
            records.append(rec)
    return records

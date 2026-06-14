"""Holdings cache store — source-agnostic read/write + diff + staleness (F81).

One JSON file per ``source_id`` under ``workspace/holdings/`` holds the latest
:class:`HoldingsSnapshot`; the previous snapshot is kept alongside as
``*.prev.json`` so the brief can show a NEW/EXIT diff. The daemon refresher is the
sole writer; the universe overlay and brief are read-only consumers (single-writer
partition, same contract as the F77 sentiment history).

Every read is lenient and fail-honest: a missing dir, a torn/corrupt file, or a
schema-drifted record is skipped, never raised — the caller degrades that one
source and the turn/universe is unaffected.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path

from loguru import logger

from src.signals.holdings.records import HoldingsDiff, HoldingsSnapshot

HOLDINGS_DIR = "holdings"

_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


def resolve_root(root: str | Path | None = None) -> Path:
    """Workspace root shared with the daemon (same contract as the F77 sweep)."""
    if root is not None:
        return Path(root)
    env = os.environ.get("AGENT_JOURNAL_ROOT")
    if env:
        return Path(env)
    from src.agent.journal import DEFAULT_ROOT  # lazy: avoid agent<->signals import cycle

    return Path(DEFAULT_ROOT)


def _safe_name(source_id: str) -> str:
    """Filesystem-safe filename stem for a source_id (e.g. ``sec_13f:0002045724``)."""
    return _SAFE_ID.sub("_", source_id.strip()) or "unknown"


def _dir(root: str | Path | None) -> Path:
    return resolve_root(root) / HOLDINGS_DIR


def snapshot_path(source_id: str, root: str | Path | None = None) -> Path:
    return _dir(root) / f"{_safe_name(source_id)}.json"


def _prev_path(source_id: str, root: str | Path | None = None) -> Path:
    return _dir(root) / f"{_safe_name(source_id)}.prev.json"


# --------------------------------------------------------------------------- #
# Write (refresher only)
# --------------------------------------------------------------------------- #
def write_snapshot(snap: HoldingsSnapshot, root: str | Path | None = None) -> Path | None:
    """Atomically persist ``snap``, rotating the prior file to ``*.prev.json``.

    Returns the written path, or None on any failure (persistence must never sink
    the refresh — NFR-1). A no-op rotation (no prior file) is fine.
    """
    try:
        cur = snapshot_path(snap.source_id, root)
        cur.parent.mkdir(parents=True, exist_ok=True)

        # Rotate the existing snapshot to .prev so we can diff against it. Only
        # rotate when the report date actually advanced, so re-fetching the same
        # filing doesn't blow away a genuinely older baseline.
        if cur.exists():
            try:
                old = read_one(snap.source_id, root)
                if old is not None and old.as_of < snap.as_of:
                    cur.replace(_prev_path(snap.source_id, root))
            except Exception as exc:  # noqa: BLE001 — diff baseline is best-effort
                logger.debug("holdings: prev rotation skipped ({})", exc)

        tmp = cur.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(snap.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(cur)  # atomic — never leaves a half-written snapshot for readers
        return cur
    except Exception as exc:  # noqa: BLE001
        logger.warning("holdings: snapshot not persisted ({}); refresh unaffected", exc)
        return None


# --------------------------------------------------------------------------- #
# Read (overlay + brief)
# --------------------------------------------------------------------------- #
def _load(path: Path) -> HoldingsSnapshot | None:
    if not path.exists():
        return None
    try:
        return HoldingsSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — corrupt/drifted file is skipped, not fatal
        logger.warning("holdings: skipping unreadable snapshot {} ({})", path.name, exc)
        return None


def read_one(source_id: str, root: str | Path | None = None) -> HoldingsSnapshot | None:
    return _load(snapshot_path(source_id, root))


def read_prev(source_id: str, root: str | Path | None = None) -> HoldingsSnapshot | None:
    return _load(_prev_path(source_id, root))


def read_snapshots(root: str | Path | None = None) -> list[HoldingsSnapshot]:
    """All current snapshots (skipping the ``*.prev.json`` baselines). Empty when
    the dir is absent or every file is unreadable."""
    d = _dir(root)
    if not d.exists():
        return []
    out: list[HoldingsSnapshot] = []
    for path in sorted(d.glob("*.json")):
        if path.name.endswith(".prev.json"):
            continue
        snap = _load(path)
        if snap is not None:
            out.append(snap)
    return out


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def is_stale(snap: HoldingsSnapshot, *, max_age_days: int, today: date | None = None) -> bool:
    """True when the filing's report date is older than ``max_age_days``.

    A manager that stops filing (or a 13F that never refreshes) ages out, so a
    long-dead disclosure can't keep injecting names forever (FR-8)."""
    today = today or date.today()
    return (today - snap.as_of).days > max_age_days


def compute_diff(prev: HoldingsSnapshot | None, cur: HoldingsSnapshot) -> HoldingsDiff:
    """NEW/EXIT ticker sets of ``cur`` vs ``prev`` (pure). Empty diff when no prev."""
    cur_set = {r.ticker for r in cur.rows}
    if prev is None:
        return HoldingsDiff()
    prev_set = {r.ticker for r in prev.rows}
    return HoldingsDiff(
        new=sorted(cur_set - prev_set),
        exited=sorted(prev_set - cur_set),
    )

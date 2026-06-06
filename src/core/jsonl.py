"""Shared JSONL helpers — the single source of truth for the project's append-only
file format (no DB; everything is JSONL under the gitignored workspace).

Two families live here:

1. **Torn-safe / atomic primitives** (``read_complete_lines``, ``atomic_write_text``,
   ``ByteCursor``) — for *cross-process* files that can be read mid-write (commands
   from the operator tool, decisions from the agent subprocess). Reads only complete
   newline-terminated lines and tracks a byte-offset cursor. Moved here from
   ``src/agent/steering/jsonl.py`` (which now re-exports them) so non-steering code
   (``surge``, the agent logs) can share them without an awkward upward dependency —
   ``core`` depends on nothing.

2. **Read-all / append helpers** (``read_records``, ``append_record``,
   ``append_records``) — for the common "load the whole log" / "append one line"
   pattern used by the equity / trades / turn logs and the surge store.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from loguru import logger


# ── torn-safe / atomic primitives (cross-process) ────────────────────────── #

def atomic_write_text(path: str | Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (temp in same dir + ``os.replace``).

    The temp name is unique per call (pid + uuid) so two writers targeting the
    same file -- or the same writer re-entered -- never share a temp and corrupt
    each other before the rename (critic #4/#6). Temp lives in the target's dir
    so ``os.replace`` stays on one filesystem.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)  # atomic on POSIX; readers never see a torn file
    except BaseException:
        tmp.unlink(missing_ok=True)  # no .tmp litter on failure
        raise


def read_complete_lines(path: str | Path, start_offset: int) -> tuple[list[str], int]:
    """Return complete lines after ``start_offset`` and the new byte offset.

    Only data up to the last ``\\n`` is consumed: a trailing partial line (a write
    in progress) is left for the next call. The returned offset is the absolute
    byte position just past the last consumed newline. If the file is missing or
    shorter than ``start_offset`` (truncated/rotated), the cursor resets to 0.
    """
    path = Path(path)
    if not path.exists():
        return [], 0
    size = path.stat().st_size
    if start_offset > size:  # truncated or rotated -> re-read from the top
        start_offset = 0
    if start_offset == size:
        return [], start_offset
    with path.open("rb") as fh:
        fh.seek(start_offset)
        chunk = fh.read()  # bytes from cursor to EOF
    last_nl = chunk.rfind(b"\n")
    if last_nl == -1:  # no complete line yet (mid-write); consume nothing
        return [], start_offset
    complete = chunk[: last_nl + 1]
    new_offset = start_offset + len(complete)
    # decode tolerantly; split into lines, dropping blanks
    text = complete.decode("utf-8", errors="replace")
    lines = [ln for ln in (raw.strip() for raw in text.split("\n")) if ln]
    return lines, new_offset


class ByteCursor:
    """A byte offset into an append-only file, persisted atomically.

    Stored as a tiny text file (the integer offset). Used so a daemon restart
    never re-processes already-consumed lines (BR-11.2).
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> int:
        try:
            return int(self.path.read_text(encoding="utf-8").strip() or "0")
        except (FileNotFoundError, ValueError):
            return 0

    def save(self, offset: int) -> None:
        atomic_write_text(self.path, str(offset))


# ── read-all / append helpers ────────────────────────────────────────────── #

def read_records(path: str | Path, model: Any = None, *, warn_skip: bool = False) -> list:
    """Load every record from a JSONL file (oldest first).

    - Missing file → ``[]``.
    - Blank lines skipped.
    - Each line is parsed with ``json.loads`` (``model=None`` → ``dict``) or
      ``model.model_validate_json`` (a pydantic model class).
    - Unparseable lines are skipped (a torn trailing line is just one such line);
      set ``warn_skip=True`` to log each skip (parity with the surge store).
    """
    path = Path(path)
    if not path.exists():
        return []
    out: list = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(model.model_validate_json(line) if model is not None else json.loads(line))
        except Exception as exc:  # JSONDecodeError or pydantic ValidationError
            if warn_skip:
                logger.warning(f"skipping unparseable line in {path}: {exc}")
            continue
    return out


def _to_line(rec: Any) -> str:
    """One JSONL line for ``rec`` — pydantic model → ``model_dump_json``, else json.dumps."""
    dump = getattr(rec, "model_dump_json", None)
    return dump() if callable(dump) else json.dumps(rec)


def append_record(path: str | Path, rec: Any) -> None:
    """Append a single record as one JSON line (creates parent dirs). Plain append
    — for atomic/torn-safe rewrites use ``atomic_write_text``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(_to_line(rec) + "\n")


def append_records(path: str | Path, recs: list) -> None:
    """Append several records (one ``open()``); no-op for an empty list."""
    if not recs:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for rec in recs:
            fh.write(_to_line(rec) + "\n")

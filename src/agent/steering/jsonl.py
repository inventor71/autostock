"""Shared torn-safe JSONL reading + atomic file writes (C-5, BR-11).

Cross-process append-only files (commands written by the operator tool, decisions
written by the agent subprocess) can be read mid-write. This module reads only
*complete* (newline-terminated) lines and tracks a **byte-offset** cursor -- never
a parsed-list index, which drifts when malformed lines are skipped (the bug in the
old ``journal.read_decisions`` + ``executor`` line-count cursor). Idempotency on
restart is the byte cursor; higher layers additionally dedup by record ``id``.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path


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

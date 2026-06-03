"""Atomic append-only index writer for early-session events.

Each completed event appends one line to ``_index.jsonl`` via ``os.replace()``.
On daemon restart, ``read_detected()`` reconstructs the set of already-seen symbols.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from src.early_session.records import EventIndex, SignalEvent, event_index_to_jsonl


class IndexWriter:
    """Manages ``workspace/early_session/{date}/_index.jsonl``."""

    def __init__(self, workspace_root: Path):
        self._root = workspace_root / "early_session"

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def append(
        self,
        event: SignalEvent,
        data_file: Path,
        bar_count: int,
        time_start: datetime,
        time_end: datetime,
    ) -> None:
        """Atomically append an EventIndex line to the date's index file."""
        date_str = event.date.isoformat() if hasattr(event.date, "isoformat") else str(event.date)
        index_dir = self._root / date_str
        index_dir.mkdir(parents=True, exist_ok=True)
        index_path = index_dir / "_index.jsonl"

        # Store the data_file path: relative to _root if under it, else filename only
        try:
            rel_path = str(data_file.relative_to(self._root))
        except ValueError:
            rel_path = data_file.name

        record = EventIndex(
            symbol=event.symbol,
            date=date_str,
            detected_at=event.detected_at.isoformat(),
            direction=event.direction,
            trigger_pct=event.trigger_pct,
            trigger_window_min=event.trigger_window_min,
            open=event.open,
            prev_close=event.prev_close,
            gap_pct=event.gap_pct,
            data_file=rel_path,
            bar_count=bar_count,
            time_range_start=time_start.isoformat(),
            time_range_end=time_end.isoformat(),
        )

        line = event_index_to_jsonl(record) + "\n"

        # Read existing → append → atomic replace
        existing = ""
        if index_path.exists():
            existing = index_path.read_text()

        tmp = tempfile.NamedTemporaryFile(
            mode="w", dir=index_dir, delete=False, suffix=".tmp"
        )
        try:
            tmp.write(existing)
            tmp.write(line)
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()
        os.replace(tmp.name, index_path)

    def read_detected(self, date_str: str) -> set[str]:
        """Return the set of symbols already detected on *date_str*."""
        index_path = self._root / date_str / "_index.jsonl"
        if not index_path.exists():
            return set()
        detected: set[str] = set()
        for line in index_path.read_text().strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                detected.add(obj["symbol"])
            except (json.JSONDecodeError, KeyError):
                continue
        return detected

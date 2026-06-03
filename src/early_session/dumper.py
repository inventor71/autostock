"""Two-phase window dumper for early-session signal events.

- ``write_before``: called immediately on detection, writes bars before the trigger.
- ``write_after``: called after the post-detection window elapses, appends bars.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.early_session.records import BarRecord, SignalEvent, bar_to_jsonl


class WindowDumper:
    """Writes event time-series as JSONL files under ``workspace/early_session/``."""

    def __init__(self, workspace_root: Path):
        self._root = workspace_root / "early_session"

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def write_before(
        self, event: SignalEvent, bars: list[BarRecord]
    ) -> Path:
        """Create a new event file and write the pre-detection bars."""
        filepath = self._event_path(event)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as fh:
            for bar in bars:
                fh.write(bar_to_jsonl(bar) + "\n")
        return filepath

    def write_after(
        self, event: SignalEvent, bars: list[BarRecord]
    ) -> Path:
        """Append post-detection bars to the existing event file."""
        filepath = self._event_path(event)
        with open(filepath, "a") as fh:
            for bar in bars:
                fh.write(bar_to_jsonl(bar) + "\n")
        return filepath

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _event_path(self, event: SignalEvent) -> Path:
        date_str = event.date.isoformat() if hasattr(event.date, "isoformat") else str(event.date)
        ts = event.detected_at.strftime("%H%M%S")
        fname = f"{event.symbol}_{ts}_{event.direction}.jsonl"
        return self._root / date_str / fname

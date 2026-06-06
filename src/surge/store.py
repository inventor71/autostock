"""JSONL store for surge records and agent analyses.

Stored under ``workspace/surge/`` — agent-accessible knowledge that the
agent both produces (analyses) and consumes (pattern reference), same class
as ``decisions.jsonl`` / ``lessons.jsonl``.
"""

from datetime import date as _date
from pathlib import Path

from loguru import logger

from src.core.jsonl import atomic_write_text, read_records as _read_records
from src.surge.records import SurgeAnalysis, SurgeRecord

_HISTORY_FILE = "history.jsonl"
_ANALYSES_FILE = "analyses.jsonl"


def _atomic_append(path: Path, lines: list[str]) -> None:
    """Append lines atomically (read existing + rewrite via temp + os.replace).

    UTF-8 throughout (read + write) — consistent with the rest of the codebase and
    with pydantic's UTF-8 ``model_dump_json``; ``atomic_write_text`` writes UTF-8.
    """
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    atomic_write_text(path, existing + "\n".join(lines) + "\n")


class SurgeStore:
    """Read/write surge records and agent analyses as JSONL.

    Default base is ``workspace/surge/`` — the agent's knowledge directory,
    consistent with ``decisions.jsonl`` and ``lessons.jsonl``.
    """

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path("workspace/surge")

    # ---- SurgeRecord ---------------------------------------------------

    @property
    def _history_path(self) -> Path:
        return self.base_dir / _HISTORY_FILE

    def write_records(self, records: list[SurgeRecord]) -> int:
        """Append new records, skipping duplicates by (symbol, date).

        Returns the number of records actually written.
        """
        if not records:
            return 0

        existing = self.read_records()
        existing_keys = {(r.symbol, r.trading_date.isoformat()) for r in existing}
        new_records = [
            r for r in records
            if (r.symbol, r.trading_date.isoformat()) not in existing_keys
        ]

        if not new_records:
            return 0

        lines = [r.model_dump_json() for r in new_records]
        _atomic_append(self._history_path, lines)
        logger.info(
            f"surge store: wrote {len(new_records)} records to {self._history_path}"
        )
        return len(new_records)

    def read_records(self, d: _date | None = None) -> list[SurgeRecord]:
        """Read surge records, optionally filtered by date."""
        records = _read_records(self._history_path, SurgeRecord, warn_skip=True)
        return [r for r in records if d is None or r.trading_date == d]

    # ---- SurgeAnalysis ------------------------------------------------

    @property
    def _analyses_path(self) -> Path:
        return self.base_dir / _ANALYSES_FILE

    def append_analysis(self, analysis: SurgeAnalysis) -> None:
        """Append a single agent analysis.

        Validates that a SurgeRecord exists for the same (symbol, date).
        Multiple analyses for the same symbol are allowed (append-only);
        consumers use the latest ``analyzed_at``.
        """
        records = self.read_records(d=analysis.trading_date)
        record_symbols = {r.symbol for r in records}
        if analysis.symbol not in record_symbols:
            raise ValueError(
                f"No SurgeRecord found for {analysis.symbol} on {analysis.trading_date}"
            )

        _atomic_append(self._analyses_path, [analysis.model_dump_json()])
        logger.info(
            f"surge store: appended analysis for {analysis.symbol} "
            f"({analysis.trading_date}) to {self._analyses_path}"
        )

    def read_analyses(self, d: _date | None = None) -> list[SurgeAnalysis]:
        """Read analyses, optionally filtered by date."""
        analyses = _read_records(self._analyses_path, SurgeAnalysis, warn_skip=True)
        return [a for a in analyses if d is None or a.trading_date == d]

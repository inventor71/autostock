"""JSONL store for surge records and agent analyses.

Stored under ``workspace/surge/`` — agent-accessible knowledge that the
agent both produces (analyses) and consumes (pattern reference), same class
as ``decisions.jsonl`` / ``lessons.jsonl``.
"""

import json
import os
import uuid
from datetime import date as _date
from pathlib import Path

from loguru import logger

from src.surge.records import SurgeAnalysis, SurgeRecord

_HISTORY_FILE = "history.jsonl"
_ANALYSES_FILE = "analyses.jsonl"


def _is_valid_json(line: str) -> bool:
    try:
        json.loads(line)
        return True
    except json.JSONDecodeError:
        return False


def _read_complete_lines(path: Path) -> list[str]:
    """Read all complete JSON lines, dropping a torn trailing line."""
    if not path.exists():
        return []
    text = path.read_text()
    lines = text.splitlines()
    if lines and not _is_valid_json(lines[-1]):
        logger.warning(f"surge store: torn last line in {path}, dropping")
        lines.pop()
    return lines


def _atomic_append(path: Path, lines: list[str]) -> None:
    """Append lines atomically via temp file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f".tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}")
    try:
        existing = path.read_text() if path.exists() else ""
        tmp_path.write_text(existing + "\n".join(lines) + "\n")
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


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
        records: list[SurgeRecord] = []
        for line in _read_complete_lines(self._history_path):
            try:
                r = SurgeRecord.model_validate_json(line)
                if d is None or r.trading_date == d:
                    records.append(r)
            except Exception:
                logger.warning(
                    f"surge store: skipping unparseable line in {self._history_path}"
                )
        return records

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
        analyses: list[SurgeAnalysis] = []
        for line in _read_complete_lines(self._analyses_path):
            try:
                a = SurgeAnalysis.model_validate_json(line)
                if d is None or a.trading_date == d:
                    analyses.append(a)
            except Exception:
                logger.warning(
                    f"surge store: skipping unparseable line in {self._analyses_path}"
                )
        return analyses

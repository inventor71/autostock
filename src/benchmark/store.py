from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from src.core.jsonl import append_record, atomic_write_text, read_records
from src.core.models import PortfolioState
from src.benchmark.models import EquitySnapshot


def _equity_path(storage_dir: str | Path, strategy: str) -> Path:
    return Path(storage_dir) / "equity" / f"{strategy}.jsonl"


class EquityRecorder:
    """Appends equity snapshots to ``<storage_dir>/equity/<strategy>.jsonl``.

    One writer (the benchmark runner thread). Reuses the shared JSONL helper so
    the format matches every other record store in the repo.
    """

    def __init__(self, storage_dir: str | Path):
        self.storage_dir = Path(storage_dir)

    def record(
        self,
        strategy: str,
        portfolio: PortfolioState,
        account_masked: str,
        ts: datetime | None = None,
    ) -> EquitySnapshot | None:
        equity = float(portfolio.equity)
        cash = float(portfolio.cash)
        # Never persist NaN/inf — a torn broker read shouldn't poison the series.
        if not (math.isfinite(equity) and math.isfinite(cash)):
            logger.warning("benchmark: non-finite equity for {} — snapshot skipped", strategy)
            return None
        snap = EquitySnapshot(
            ts=ts or datetime.utcnow(),
            strategy=strategy,
            account_masked=account_masked,
            equity=equity,
            cash=cash,
            position_count=portfolio.position_count,
        )
        append_record(_equity_path(self.storage_dir, strategy), snap)
        return snap

    def load(self, strategy: str) -> list[EquitySnapshot]:
        return read_records(_equity_path(self.storage_dir, strategy), EquitySnapshot)

    def compact(self, strategy: str, retention_days: int, now: datetime | None = None) -> int:
        """Drop snapshots older than ``retention_days``. Returns #records kept.

        Atomic rewrite (torn-safe). No-op if the file is absent or fully within
        retention. Keeps the source series long enough for re-analysis (NFR-4)
        while bounding growth (NFR-3).
        """
        path = _equity_path(self.storage_dir, strategy)
        records = self.load(strategy)
        if not records:
            return 0
        cutoff = (now or datetime.utcnow()) - timedelta(days=retention_days)
        kept = [r for r in records if r.ts >= cutoff]
        if len(kept) != len(records):
            text = "".join(r.model_dump_json() + "\n" for r in kept)
            atomic_write_text(path, text)
            logger.info(
                "benchmark: compacted {} ({} -> {} snapshots)",
                strategy, len(records), len(kept),
            )
        return len(kept)

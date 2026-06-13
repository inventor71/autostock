"""Persistent store for intraday-shape feature records (P0).

Parquet-backed, one file per symbol under ``data/intraday/`` (gitignored). Parquet
preserves column dtypes and compresses the columnar numeric feature set far better
than the original CSV, while the public contract — ``upsert`` / ``read`` keyed by
``(date, symbol)`` — stays the swap point untouched by callers.

Legacy ``<SYMBOL>.csv`` files (the original backend) are migrated to Parquet once,
lazily, on first access: each is read, written as ``<SYMBOL>.parquet``, and the
source renamed to ``<SYMBOL>.csv.migrated`` so it is neither re-read nor lost. The
``date`` column is kept as an ISO string (callers sort/dedupe/stringify on it), so
round-tripping through Parquet preserves the exact behaviour the CSV backend had.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.data.intraday.features import FEATURE_COLUMNS


class IntradayFeatureStore:
    """Append/read intraday feature records, idempotent on ``(date, symbol)``."""

    def __init__(self, root: Path | str = "data/intraday") -> None:
        self.root = Path(root)

    def _path(self, symbol: str) -> Path:
        return self.root / f"{symbol.upper()}.parquet"

    def _migrate_legacy(self) -> None:
        """One-time CSV→Parquet migration for any legacy ``*.csv`` in the store.

        Idempotent: a CSV whose Parquet sibling already exists is treated as stale
        (renamed aside, not re-imported); otherwise it is converted. Renamed CSVs
        end in ``.csv.migrated`` so subsequent scans skip them.
        """
        if not self.root.exists():
            return
        for csv_path in sorted(self.root.glob("*.csv")):
            parquet_path = csv_path.with_suffix(".parquet")
            if not parquet_path.exists():
                pd.read_csv(csv_path).to_parquet(parquet_path, index=False)
            csv_path.rename(csv_path.with_suffix(".csv.migrated"))

    def upsert(self, records: Iterable[dict]) -> int:
        """Insert/replace feature rows. Re-running a date overwrites that row.

        Returns the number of rows written across all touched symbols.
        """
        new = pd.DataFrame(list(records))
        if new.empty:
            return 0
        new = new.reindex(columns=FEATURE_COLUMNS)
        self.root.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy()

        written = 0
        for symbol, group in new.groupby("symbol", sort=True):
            path = self._path(str(symbol))
            if path.exists():
                existing = pd.read_parquet(path)
                combined = pd.concat([existing, group], ignore_index=True)
            else:
                combined = group
            # Last write wins for a repeated date; keep one row per date, sorted.
            combined = (
                combined.drop_duplicates(subset="date", keep="last")
                .sort_values("date")
                .reset_index(drop=True)
                .reindex(columns=FEATURE_COLUMNS)
            )
            combined.to_parquet(path, index=False)
            written += len(group)
        return written

    def read(
        self,
        symbols: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> pd.DataFrame:
        """Read stored features, optionally filtered by symbol and date range.

        Returns an empty, correctly-columned DataFrame when nothing matches.
        """
        self._migrate_legacy()
        if symbols is None:
            paths = sorted(self.root.glob("*.parquet")) if self.root.exists() else []
        else:
            paths = [self._path(s) for s in symbols]

        frames = [pd.read_parquet(p) for p in paths if p.exists()]
        if not frames:
            return pd.DataFrame(columns=FEATURE_COLUMNS)

        df = pd.concat(frames, ignore_index=True)
        d = pd.to_datetime(df["date"]).dt.date
        if start is not None:
            df = df[d >= start]
            d = d[df.index]
        if end is not None:
            df = df[d <= end]
        return (
            df.sort_values(["symbol", "date"])
            .reset_index(drop=True)
            .reindex(columns=FEATURE_COLUMNS)
        )

    def symbols(self) -> list[str]:
        """Symbols currently present in the store."""
        if not self.root.exists():
            return []
        self._migrate_legacy()
        return sorted(p.stem for p in self.root.glob("*.parquet"))

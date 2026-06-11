"""Persistent store for intraday-shape feature records (P0).

CSV-backed, one file per symbol under ``data/intraday/`` (gitignored). Chosen to
avoid a new dependency (pyarrow is absent; pandas is present) and to keep the
exploratory dataset human-inspectable. The public contract — ``upsert`` /
``read`` keyed by ``(date, symbol)`` — is the swap point: a Parquet/DuckDB backend
can replace the body later without touching callers.
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
        return self.root / f"{symbol.upper()}.csv"

    def upsert(self, records: Iterable[dict]) -> int:
        """Insert/replace feature rows. Re-running a date overwrites that row.

        Returns the number of rows written across all touched symbols.
        """
        new = pd.DataFrame(list(records))
        if new.empty:
            return 0
        new = new.reindex(columns=FEATURE_COLUMNS)
        self.root.mkdir(parents=True, exist_ok=True)

        written = 0
        for symbol, group in new.groupby("symbol", sort=True):
            path = self._path(str(symbol))
            if path.exists():
                existing = pd.read_csv(path)
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
            combined.to_csv(path, index=False)
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
        if symbols is None:
            paths = sorted(self.root.glob("*.csv")) if self.root.exists() else []
        else:
            paths = [self._path(s) for s in symbols]

        frames = [pd.read_csv(p) for p in paths if p.exists()]
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
        return sorted(p.stem for p in self.root.glob("*.csv"))

"""Daemon-side holdings refresh job (F81, FR-2/FR-7) — the only HTTP path.

Mirrors the F77 ``SentimentSweeper``: a scheduled tick fetches each provider's
latest snapshot and writes it to ``workspace/holdings/``; the research turn and
universe resolution only READ that cache. Boring and unkillable — every provider
failure degrades that one source and nothing propagates into the scheduler
(NFR-1, same contract as the wake detector).
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.signals.holdings.provider import HoldingsProvider
from src.signals.holdings.store import write_snapshot


class HoldingsRefresher:
    def __init__(
        self,
        *,
        providers: list[HoldingsProvider],
        root: str | Path | None = None,
    ):
        self._providers = list(providers)
        self._root = root

    def refresh_tick(self) -> None:
        """Refresh every provider once. Never raises."""
        try:
            self._refresh()
        except Exception as exc:  # belt-and-braces: never kill the scheduler
            logger.error("holdings refresh failed (continuing): {}", exc)

    def _refresh(self) -> None:
        if not self._providers:
            return
        ok = 0
        failed = 0
        for provider in self._providers:
            try:
                snap = provider.fetch_snapshot()
            except Exception as exc:  # noqa: BLE001 — one source down never blocks others
                failed += 1
                logger.warning("holdings: {} refresh failed ({})", provider.source_id, exc)
                continue
            if write_snapshot(snap, root=self._root) is not None:
                ok += 1
                logger.info(
                    "holdings: {} refreshed — {} rows, {} unmapped, as_of {}",
                    snap.source_id, len(snap.rows), snap.unmapped_n, snap.as_of,
                )
        logger.info("holdings refresh: {} ok, {} failed", ok, failed)

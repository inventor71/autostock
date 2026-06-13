"""Hourly StockTwits universe sweep — the daemon job body (F77, FR-2).

Plain HTTP (no LLM cost): one unauthenticated symbol-stream call per universe
symbol, label aggregates appended to ``workspace/sentiment/``. Designed to be
boring and unkillable:

- runs only inside the configured ET window;
- paces requests (``request_gap_s``) and hard-caps the tick at
  ``hourly_budget`` requests so we stay inside StockTwits' ~200/hr
  unauthenticated allowance (NFR-3);
- a 429/403 aborts the WHOLE tick (back off, retry next tick) instead of
  hammering on; partial results are still persisted;
- any exception is absorbed here — nothing propagates into the scheduler
  (NFR-1, same contract as the wake detector).
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from loguru import logger

from src.core.markettime import ET
from src.signals.records import SentimentRecord
from src.signals.sentiment import append_sweep
from src.signals.settings import SentimentConfig
from src.signals.sources.stocktwits import RateLimited, StocktwitsSource


def _in_window(now_et: datetime, window: tuple[str, str]) -> bool:
    start, end = window
    hhmm = now_et.strftime("%H:%M")
    return start <= hhmm <= end


class SentimentSweeper:
    def __init__(
        self,
        *,
        source: StocktwitsSource,
        universe: list[str],
        cfg: SentimentConfig,
        root: str | Path | None = None,
        now_fn: Callable[[], datetime] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        self._source = source
        self._universe = list(universe)
        self._cfg = cfg
        self._root = root
        self._now = now_fn or (lambda: datetime.now(ET))
        self._sleep = sleep_fn

    def sweep_tick(self) -> None:
        """One sweep over the universe. Never raises."""
        try:
            self._sweep()
        except Exception as exc:  # belt-and-braces: never kill the scheduler
            logger.error("sentiment sweep failed (continuing): {}", exc)

    def _sweep(self) -> None:
        cfg = self._cfg
        if not cfg.enabled:
            return
        now_et = self._now().astimezone(ET)
        if not _in_window(now_et, cfg.window_et):
            return

        records: list[SentimentRecord] = []
        requests_made = 0
        skipped = 0
        aborted: str | None = None
        for i, symbol in enumerate(self._universe):
            if requests_made >= cfg.hourly_budget:
                aborted = f"budget {cfg.hourly_budget} reached"
                break
            if i > 0 and cfg.request_gap_s > 0:
                self._sleep(cfg.request_gap_s)
            requests_made += 1
            try:
                records.append(self._source.fetch_symbol(symbol))
            except RateLimited as exc:
                aborted = str(exc)
                break
            except Exception as exc:
                skipped += 1
                logger.debug("sentiment sweep: {} skipped ({})", symbol, exc)

        if records:
            append_sweep(records, root=self._root)
        if aborted:
            logger.warning(
                "sentiment sweep aborted after {} request(s) ({}); "
                "{} symbol(s) collected, retrying next tick",
                requests_made, aborted, len(records),
            )
        else:
            logger.info(
                "sentiment sweep: {} collected, {} skipped, {} request(s)",
                len(records), skipped, requests_made,
            )

"""Orchestrator that runs the early-session detection loop.

Lifecycle:
- ``start()``: called at market open (09:30 ET) to begin polling.
- ``tick()``: fetch → buffer → detect → dump, every *poll_interval_seconds*.
- ``stop()``: called at the configured ET end time (or when all pending
  finalizes complete).

All wall-clock comparisons are done in **US/Eastern** (the market timezone),
matching the rest of the codebase (``zoneinfo.ZoneInfo("America/New_York")``).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from loguru import logger

from src.core.types import TimeFrame
from src.early_session.buffer import BufferManager
from src.early_session.config import EarlySessionConfig
from src.early_session.detector import SignalDetector
from src.early_session.dumper import WindowDumper
from src.early_session.index_writer import IndexWriter
from src.early_session.records import BarRecord, SignalEvent

_ET = ZoneInfo("America/New_York")


class EarlySessionMonitor:
    """Top-level orchestrator for early-session signal detection.

    Owns the buffer, detector, dumper, and index writer.  Designed to be driven
    by a single APScheduler job thread (P2 — ``max_instances=1``, ``coalesce=True``).
    """

    def __init__(
        self,
        config: EarlySessionConfig,
        data_provider,
        workspace_root: Path,
        symbols: list[str] | Callable[[], list[str]] | None = None,
    ):
        self._config = config
        self._data_provider = data_provider
        self._workspace_root = workspace_root
        # Universe resolver: an explicit list, a callable returning one (e.g. the
        # agent's live universe), or None to fall back to config/settings.
        self._symbols_src = symbols

        # The buffer must retain the whole dump window (before + after), not just
        # the configured minimum — see EarlySessionConfig.effective_retention_minutes.
        self._buffer = BufferManager(
            retention_minutes=config.effective_retention_minutes
        )
        self._detector = SignalDetector(
            threshold_pct=config.threshold_pct,
            window_minutes=config.window_minutes,
        )
        self._dumper = WindowDumper(workspace_root)
        self._index_writer = IndexWriter(workspace_root)

        self._detected_today: set[str] = set()
        # symbol → (detected event, datetime when the after-dump window ends).
        # The event is kept so finalize never has to re-detect/reconstruct it.
        self._pending_finalizes: dict[str, tuple[SignalEvent, datetime]] = {}

        self._monitor_end: datetime | None = None
        self._running = False

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Begin monitoring. Restores previously-detected symbols from the index."""
        if not self._config.enabled:
            logger.info("Early-session monitor disabled — skipping")
            return

        now = datetime.now(_ET)
        self._detected_today = self._index_writer.read_detected(
            now.strftime("%Y-%m-%d")
        )

        h, m = map(int, self._config.monitor_end_et.split(":"))
        self._monitor_end = now.replace(hour=h, minute=m, second=0, microsecond=0)

        self._running = True
        logger.info(
            "Early-session monitor started | {} symbols | threshold ±{}%/{}min | "
            "dump -{}m/+{}m | poll {}s | end {}",
            len(self._symbols()),
            self._config.threshold_pct,
            self._config.window_minutes,
            self._config.dump_before_minutes,
            self._config.dump_after_minutes,
            self._config.poll_interval_seconds,
            self._monitor_end.isoformat() if self._monitor_end else "N/A",
        )

    def tick(self) -> None:
        """One poll cycle: fetch → buffer → detect → dump → finalize."""
        if not self._running:
            return

        now = datetime.now(_ET)

        # --- 1. fetch -------------------------------------------------------
        symbols = self._symbols()
        if not symbols:
            return

        try:
            bars_batch = self._data_provider.get_bars(
                symbols,
                timeframe=TimeFrame.MINUTE_1,
                limit=2,
            )
        except Exception:
            logger.opt(exception=True).warning("Early-session batch fetch failed — skipping tick")
            return

        # --- 2. buffer ------------------------------------------------------
        for sym, df in (bars_batch or {}).items():
            for ts, row in df.iterrows():
                self._buffer.push(sym, BarRecord.from_alpaca_bar(sym, ts, row))

        # --- 3. detect ------------------------------------------------------
        for sym in symbols:
            if sym in self._detected_today or sym in self._pending_finalizes:
                continue
            window = self._buffer.get_window(sym, self._config.window_minutes)
            event = self._detector.detect(window)
            if event is None:
                continue

            # Fill in open/prev_close/gap from the buffer
            day_bars = self._buffer.get_range(
                sym,
                now.replace(hour=0, minute=0, second=0, microsecond=0),
                now,
            )
            if day_bars:
                event.open = day_bars[0].open
            prev_close = self._resolve_prev_close(sym, now)
            event.prev_close = prev_close
            if prev_close and event.open:
                event.gap_pct = round((event.open - prev_close) / prev_close * 100, 2)

            self._detected_today.add(sym)
            logger.info(
                "Early-session signal: {} {} {:+0.2f}% in {}min",
                sym, event.direction, event.trigger_pct, event.trigger_window_min,
            )

            # --- 3a. dump before-window -------------------------------------
            start = event.detected_at - timedelta(minutes=self._config.dump_before_minutes)
            before_bars = self._buffer.get_range(sym, start, event.detected_at)
            self._dumper.write_before(event, before_bars)

            # --- 3b. schedule finalize (keep the event for later) -----------
            finalize_at = now + timedelta(minutes=self._config.dump_after_minutes)
            self._pending_finalizes[sym] = (event, finalize_at)

        # --- 4. finalize completed events -----------------------------------
        for sym, (event, finalize_at) in list(self._pending_finalizes.items()):
            if now < finalize_at:
                continue

            # Use the SignalEvent captured at detection time — never re-detect.
            after_start = finalize_at - timedelta(minutes=self._config.dump_after_minutes)
            after_bars = self._buffer.get_range(sym, after_start, now)
            data_file = self._dumper.write_after(event, after_bars)

            total_bars = len(
                self._buffer.get_range(
                    sym,
                    after_start - timedelta(minutes=self._config.dump_before_minutes),
                    now,
                )
            )
            self._index_writer.append(event, data_file, total_bars, after_start, now)

            logger.info("Early-session dump finalized: {} → {}", sym, data_file)
            del self._pending_finalizes[sym]

        # --- 5. stop check --------------------------------------------------
        if self._monitor_end and now >= self._monitor_end and not self._pending_finalizes:
            self.stop()

    def stop(self) -> None:
        """Stop monitoring."""
        self._running = False
        logger.info("Early-session monitor stopped | {} events today", len(self._detected_today))

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _symbols(self) -> list[str]:
        """Resolve the universe: injected list/callable, else config/settings."""
        src = self._symbols_src
        if callable(src):
            try:
                return list(src())
            except Exception:
                logger.opt(exception=True).warning("Early-session symbols callable failed")
                return []
        if src is not None:
            return list(src)
        # Fallback: the provider-resolved trading universe (F30 replaced the
        # static trading.symbols list with resolve_universe).
        try:
            from config.config import get_settings
            from src.universe.factory import resolve_universe
            return list(resolve_universe(get_settings()))
        except Exception:
            return []

    def _resolve_prev_close(self, symbol: str, now: datetime) -> float:
        """Try to get the previous trading day's close for *symbol*."""
        try:
            df = self._data_provider.get_bars(
                symbol,
                timeframe=TimeFrame.DAY_1,
                limit=2,
            )
            if isinstance(df, dict):
                df = df.get(symbol)
            if df is not None and not df.empty and len(df) >= 2:
                return float(df.iloc[-2]["close"])
        except Exception:
            pass
        return 0.0

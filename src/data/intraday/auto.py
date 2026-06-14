"""Automated intraday feature collection (F82): gap-aware backfill + EOD append.

Thin orchestration over ``collector.collect()`` and ``IntradayFeatureStore``. The
collector already fetches/sessionizes/computes/upserts per symbol with per-symbol
failure isolation; this module decides *what range each symbol still needs* and
appends the current day's session after the close. Everything is pure and
injectable (provider / store / ``today``) so the gap logic is unit-testable
without a network or a real scheduler — the daemon wiring stays a thin caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from loguru import logger

from src.core.types import TimeFrame
from src.data.intraday.collector import collect
from src.data.intraday.store import IntradayFeatureStore


@dataclass(frozen=True)
class CollectionConfig:
    """``intraday_collection`` settings block (read straight from yaml, like the
    surge / early-session / sentiment configs, since ``Settings(extra="ignore")``
    drops unknown blocks). Default ON — the daemon backfills + appends once wired."""

    enabled: bool = True
    backfill_years: int = 3
    provider: str = "alpaca"
    timeframe: str = "5m"

    @classmethod
    def from_yaml(cls, cfg: dict | None) -> "CollectionConfig":
        block = (cfg or {}).get("intraday_collection") or {}
        return cls(
            enabled=bool(block.get("enabled", True)),
            backfill_years=int(block.get("backfill_years", 3)),
            provider=str(block.get("provider", "alpaca")),
            timeframe=str(block.get("timeframe", "5m")),
        )


def last_session_date(store: IntradayFeatureStore, symbol: str) -> date | None:
    """Most recent stored session date for ``symbol`` (None if unstored)."""
    df = store.read([symbol])
    if df.empty:
        return None
    # store.read sorts ascending by (symbol, date); date is an ISO string.
    return date.fromisoformat(str(df["date"].iloc[-1]))


def backfill_window(
    last: date | None, *, today: date, backfill_years: int
) -> tuple[date, date] | None:
    """Range a symbol still needs, or None when already current.

    - unstored        -> (today - backfill_years, today): full history.
    - stale (< today-1) -> (last+1, today): incremental top-up.
    - current         -> None: skip.

    Weekends/holidays need no special-casing: the provider returns no bars for
    them, so they collapse to zero sessions naturally.
    """
    if last is None:
        return (today - timedelta(days=backfill_years * 365), today)
    if last < today - timedelta(days=1):
        return (last + timedelta(days=1), today)
    return None


def _at_midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


def backfill_universe(
    provider,
    store: IntradayFeatureStore,
    symbols: list[str],
    *,
    today: date,
    backfill_years: int,
    timeframe: TimeFrame = TimeFrame.MINUTE_5,
) -> dict[str, int]:
    """Backfill each symbol's missing range. Returns ``{symbol: sessions_written}``.

    Per-symbol fetch failures are isolated inside ``collect`` (logged, recorded as
    0) so one bad symbol never aborts the sweep.
    """
    summary: dict[str, int] = {}
    for symbol in symbols:
        window = backfill_window(
            last_session_date(store, symbol), today=today, backfill_years=backfill_years
        )
        if window is None:
            summary[symbol] = 0
            continue
        start, end = window
        res = collect(
            provider, [symbol], store,
            timeframe=timeframe, start=_at_midnight(start), end=_at_midnight(end),
        )
        summary[symbol] = res.get(symbol, 0)
    logger.info(
        "intraday backfill: {} symbol(s), {} session(s) written",
        len(symbols), sum(summary.values()),
    )
    return summary


def collect_today(
    provider,
    store: IntradayFeatureStore,
    symbols: list[str],
    *,
    today: date,
    timeframe: TimeFrame = TimeFrame.MINUTE_5,
    lookback_days: int = 4,
) -> dict[str, int]:
    """Append recent sessions (through ``today``) for ``symbols`` and upsert.

    Uses a date-range fetch over the last ``lookback_days`` — the path the
    Alpaca IEX/SIP feeds serve reliably (a bare ``limit`` can come back empty),
    and it self-heals a missed prior day within the window. ``end`` spans today's
    full session. Idempotent on (date, symbol). Returns ``{symbol: sessions}``.
    """
    start = _at_midnight(today - timedelta(days=lookback_days))
    end = _at_midnight(today) + timedelta(days=1)  # include all of today's bars
    res = collect(provider, symbols, store, timeframe=timeframe, start=start, end=end)
    logger.info(
        "intraday EOD collect: {} session(s) across {} symbol(s)",
        sum(res.values()), len(symbols),
    )
    return res

"""Collect intraday-shape features for the universe and persist them (P0).

Fetches intraday bars for each symbol via an injected ``BaseDataProvider``, splits
them into sessions, computes per-session features, and upserts them into an
``IntradayFeatureStore``. Deterministic and network-free under tests (the provider
and store are injected); ``__main__`` wires the real yfinance provider + universe.

Provider history note: yfinance intraday is capped (~60 days for 5m bars). For a
deep multi-year backtest, point ``--provider alpaca`` at a date range (Alpaca
serves minute bars back to 2016; the free IEX feed is a volume subset). Either way
the store accumulates forward over subsequent runs.

Run:
    python -m src.data.intraday_collector backfill --days 30 [--symbols AAPL MSFT]
    python -m src.data.intraday_collector backfill --provider alpaca \
        --start 2022-01-01 [--end 2024-01-01] [--timeframe 5m] [--symbols AAPL]
    python -m src.data.intraday_collector today    [--symbols AAPL MSFT]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime

import pandas as pd
from loguru import logger

from src.core.types import TimeFrame
from src.data.intraday_features import compute_session_features
from src.data.intraday_store import IntradayFeatureStore


def sessionize(bars: pd.DataFrame) -> list[tuple[date, pd.DataFrame]]:
    """Split a multi-day intraday frame into ``(date, session_bars)`` pairs.

    Sessions are ordered ascending so the prior session's close is available as
    the next session's gap reference.
    """
    if bars is None or bars.empty:
        return []
    bars = bars.sort_index()
    session_dates = pd.Index(bars.index).map(lambda ts: ts.date())
    out: list[tuple[date, pd.DataFrame]] = []
    for d, group in bars.groupby(session_dates):
        out.append((d, group))
    out.sort(key=lambda pair: pair[0])
    return out


def features_for_symbol(
    symbol: str,
    bars: pd.DataFrame,
    *,
    min_bars: int = 5,
) -> list[dict]:
    """Compute per-session feature records from one symbol's intraday bars.

    ``prev_close`` for each session is the prior session's close within the same
    fetched frame (None for the earliest session). Sessions with fewer than
    ``min_bars`` bars are skipped (too sparse to characterise a shape).
    """
    records: list[dict] = []
    prev_close: float | None = None
    for session_date, session in sessionize(bars):
        if len(session) < min_bars:
            prev_close = float(session["close"].iloc[-1])
            continue
        try:
            records.append(
                compute_session_features(
                    session,
                    symbol=symbol,
                    session_date=session_date,
                    prev_close=prev_close,
                )
            )
        except ValueError as exc:  # fail-closed per session, keep going
            logger.warning(f"skip {symbol} {session_date}: {exc}")
        prev_close = float(session["close"].iloc[-1])
    return records


def collect(
    provider,
    symbols: list[str],
    store: IntradayFeatureStore,
    *,
    timeframe: TimeFrame = TimeFrame.MINUTE_5,
    limit: int = 4000,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, int]:
    """Fetch, compute and upsert intraday features for ``symbols``.

    When ``start``/``end`` are given, bars are fetched by date range (limit
    removed) — the path for a deep Alpaca backfill. Otherwise the most recent
    ``limit`` bars are fetched (the quick yfinance path).

    Returns ``{symbol: sessions_written}``. A symbol whose fetch fails is logged
    and recorded as 0 rather than aborting the batch.
    """
    use_range = start is not None or end is not None
    summary: dict[str, int] = {}
    for symbol in symbols:
        try:
            if use_range:
                bars = provider.get_bars(
                    symbol, timeframe=timeframe, start=start, end=end, limit=None
                )
            else:
                bars = provider.get_bars(symbol, timeframe=timeframe, limit=limit)
        except Exception as exc:
            logger.warning(f"fetch failed for {symbol}: {exc}")
            summary[symbol] = 0
            continue
        records = features_for_symbol(symbol, bars)
        store.upsert(records)
        summary[symbol] = len(records)
        logger.info(f"{symbol}: {len(records)} sessions")
    return summary


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _provider(name: str, settings):
    """Build a data provider by name (CLI composition root)."""
    if name == "alpaca":
        from src.data.providers.alpaca_provider import AlpacaDataProvider

        return AlpacaDataProvider(
            api_key=settings.alpaca_api_key, secret_key=settings.alpaca_secret_key
        )
    from src.data.providers.yfinance_provider import YFinanceProvider

    return YFinanceProvider()


def main(argv: list[str] | None = None) -> int:
    from config.config import get_settings

    parser = argparse.ArgumentParser(prog="python -m src.data.intraday_collector")
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in ("backfill", "today"):
        p = sub.add_parser(name)
        p.add_argument("--symbols", nargs="*", default=None, help="default: configured universe")
        p.add_argument("--timeframe", default="5m", help="bar interval (default 5m)")
        p.add_argument(
            "--provider",
            choices=["yfinance", "alpaca"],
            default="yfinance",
            help="data source (alpaca for deep history; default yfinance)",
        )
    bf = sub.choices["backfill"]
    bf.add_argument(
        "--days", type=int, default=30, help="recent days to request (limit-based path)"
    )
    bf.add_argument(
        "--start", default=None, help="YYYY-MM-DD; switches to date-range fetch (use with alpaca)"
    )
    bf.add_argument("--end", default=None, help="YYYY-MM-DD; defaults to today when --start is set")

    args = parser.parse_args(argv)
    settings = get_settings()
    symbols = args.symbols or list(settings.trading.symbols)
    timeframe = TimeFrame(args.timeframe)
    store = IntradayFeatureStore()

    start = end = None
    if getattr(args, "start", None):
        start = datetime.strptime(args.start, "%Y-%m-%d")
        end = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.now()

    # Limit-based path sizing: ~78 five-minute regular-hours bars/session.
    bars_per_session = max(1, TimeFrame.DAY_1.minutes // max(1, timeframe.minutes) // 4)
    limit = getattr(args, "days", 3) * bars_per_session

    summary = collect(
        _provider(args.provider, settings),
        symbols,
        store,
        timeframe=timeframe,
        limit=limit,
        start=start,
        end=end,
    )
    json.dump(
        {"provider": args.provider, "written": summary, "store": str(store.root)},
        sys.stdout,
        indent=2,
        default=str,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""Collect DecisionOutcome records by joining decisions, fills, and price data."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf
from loguru import logger

from src.agent.journal import Decision, Journal
from src.agent.quality.models import (
    DecisionOutcome,
    ExecutionRecord,
    OHLC,
    RoundTrip,
)
from src.core.trades import match_round_trips


def _load_execution_log(journal_root: Path) -> list[ExecutionRecord]:
    log_file = journal_root / "execution_log.jsonl"
    if not log_file.exists():
        return []
    records = []
    for line in log_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(ExecutionRecord.model_validate_json(line))
        except Exception:
            continue
    return records


def _fills_to_dicts(fills) -> list[dict]:
    """Convert FillEvent (Pydantic) or dict fills to match_round_trips input."""
    out = []
    for f in fills:
        if isinstance(f, dict):
            out.append(f)
        else:
            out.append({
                "symbol": f.symbol,
                "side": f.side,
                "qty": float(f.qty),
                "price": float(f.price),
                "ts": f.ts.isoformat() if hasattr(f.ts, "isoformat") else str(f.ts),
            })
    return out


def _fetch_daily_ohlc(
    symbols: list[str],
    start: datetime,
    end: datetime,
) -> dict[str, pd.DataFrame]:
    """Batch-fetch daily OHLC for multiple symbols via yfinance."""
    cache: dict[str, pd.DataFrame] = {}
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    for sym in symbols:
        try:
            df = yf.download(sym, start=start_str, end=end_str, progress=False)
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                cache[sym] = df
        except Exception as exc:
            logger.warning(f"yfinance fetch failed for {sym}: {exc}")
    return cache


def _slice_price_path(
    ohlc_cache: dict[str, pd.DataFrame],
    symbol: str,
    opened_at: str,
    closed_at: str,
) -> list[OHLC]:
    df = ohlc_cache.get(symbol)
    if df is None or df.empty:
        return []
    try:
        start = pd.Timestamp(opened_at).tz_localize(None)
        end = pd.Timestamp(closed_at).tz_localize(None)
    except Exception:
        return []
    mask = (df.index >= start) & (df.index <= end)
    sliced = df.loc[mask]
    return [
        OHLC(
            date=str(row.Index.date()) if hasattr(row.Index, "date") else str(row.Index),
            open=float(row.Open),
            high=float(row.High),
            low=float(row.Low),
            close=float(row.Close),
        )
        for row in sliced.itertuples()
    ]


def _match_decision_to_execution(
    d: Decision,
    d_index: int,
    exec_records: list[ExecutionRecord],
) -> ExecutionRecord | None:
    for er in exec_records:
        if er.decision_index == d_index and er.symbol == d.symbol:
            return er
    return None


def _heuristic_match(
    d: Decision,
    exec_records: list[ExecutionRecord],
) -> ExecutionRecord | None:
    """Fallback: match by symbol + action + closest timestamp."""
    candidates = [
        er for er in exec_records
        if er.symbol == d.symbol and er.action == d.action
    ]
    if not candidates:
        return None
    try:
        d_ts = d.ts.timestamp() if hasattr(d.ts, "timestamp") else 0
        return min(
            candidates,
            key=lambda er: abs(datetime.fromisoformat(er.ts).timestamp() - d_ts),
        )
    except Exception:
        return candidates[0] if candidates else None


def _match_to_round_trip(
    symbol: str,
    exec_record: ExecutionRecord | None,
    round_trips: list[dict],
) -> RoundTrip | None:
    """Find the round-trip that contains this execution's entry."""
    if exec_record is None:
        return None
    for rt in round_trips:
        if rt["symbol"] != symbol:
            continue
        if abs(rt["entry_price"] - exec_record.filled_price) < 0.02:
            return RoundTrip(**rt)
    return None


def collect_outcomes(
    journal: Journal,
    fills: list | None = None,
    lookback_days: int = 30,
) -> list[DecisionOutcome]:
    """Build DecisionOutcome list from all available data sources.

    Args:
        journal: Journal instance (for decisions + execution_log).
        fills: Pre-fetched fills (FillEvent or dict). If None, skips fill-based matching.
        lookback_days: Extra days of price data to fetch after the last decision.
    """
    decisions = journal.read_decisions()
    buy_sell = [
        (i, d) for i, d in enumerate(decisions)
        if d.action in ("BUY", "SELL")
    ]
    if not buy_sell:
        return []

    exec_records = _load_execution_log(journal.root)

    fill_dicts = _fills_to_dicts(fills) if fills else []
    round_trips = match_round_trips(fill_dicts) if fill_dicts else []

    symbols = sorted({d.symbol for _, d in buy_sell})
    earliest = min(d.ts for _, d in buy_sell)
    latest = max(d.ts for _, d in buy_sell)
    ohlc_cache = _fetch_daily_ohlc(
        symbols,
        start=earliest - timedelta(days=1),
        end=latest + timedelta(days=lookback_days),
    )

    # Benchmark data
    for bench in ("SPY", "QQQ"):
        if bench not in ohlc_cache:
            ohlc_cache.update(
                _fetch_daily_ohlc(
                    [bench],
                    start=earliest - timedelta(days=1),
                    end=latest + timedelta(days=lookback_days),
                )
            )

    outcomes: list[DecisionOutcome] = []
    used_exec: set[int] = set()

    for d_index, d in buy_sell:
        er = _match_decision_to_execution(d, d_index, exec_records)
        method = "execution_log"
        if er is None:
            er = _heuristic_match(d, exec_records)
            method = "heuristic" if er is not None else "unmatched"

        if er is not None:
            er_id = id(er)
            if er_id in used_exec:
                er = None
                method = "unmatched"
            else:
                used_exec.add(er_id)

        rt = _match_to_round_trip(d.symbol, er, round_trips)

        if rt is not None:
            price_path = _slice_price_path(
                ohlc_cache, d.symbol, rt.opened_at, rt.closed_at
            )
        else:
            price_path = _slice_price_path(
                ohlc_cache, d.symbol,
                d.ts.isoformat(),
                (d.ts + timedelta(days=lookback_days)).isoformat(),
            )

        outcomes.append(DecisionOutcome(
            decision=d,
            execution=er,
            round_trip=rt,
            price_path=price_path,
            match_method=method,
        ))

    return outcomes

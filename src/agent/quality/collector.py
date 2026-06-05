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
from src.agent.steering.jsonl import read_complete_lines
from src.core.trades import match_round_trips


def _load_execution_log(journal_root: Path) -> list[ExecutionRecord]:
    log_file = journal_root / "execution_log.jsonl"
    if not log_file.exists():
        return []
    records = []
    try:
        lines, _ = read_complete_lines(log_file, 0)
    except Exception as exc:
        logger.warning(f"Failed to read execution log: {exc}")
        return []
    for line in lines:
        line = line.strip() if isinstance(line, str) else line.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            records.append(ExecutionRecord.model_validate_json(line))
        except Exception:
            logger.debug(f"Skipping unparseable execution log line")
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


def _to_naive_ts(ts_str: str) -> pd.Timestamp | None:
    """Parse a timestamp string and return a naive (tz-stripped) Timestamp normalized to midnight.

    Handles both aware (UTC, offset) and naive strings. Returns None on parse failure.
    """
    try:
        ts = pd.Timestamp(ts_str)
    except Exception:
        return None
    # Convert to naive UTC-equivalent, then normalize to midnight
    if ts.tz is not None:
        ts = ts.tz_convert(None)
    return ts.normalize()


def _slice_price_path(
    ohlc_cache: dict[str, pd.DataFrame],
    symbol: str,
    opened_at: str,
    closed_at: str,
) -> list[OHLC]:
    df = ohlc_cache.get(symbol)
    if df is None or df.empty:
        return []
    start = _to_naive_ts(opened_at)
    end = _to_naive_ts(closed_at)
    if start is None or end is None:
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


def _parse_exec_ts(ts_str: str) -> float | None:
    """Parse execution record timestamp to a UTC epoch float for comparison."""
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _heuristic_match(
    d: Decision,
    exec_records: list[ExecutionRecord],
) -> ExecutionRecord | None:
    """Fallback: match by symbol + action + closest timestamp (UTC-normalized)."""
    candidates = [
        er for er in exec_records
        if er.symbol == d.symbol and er.action == d.action
    ]
    if not candidates:
        return None

    # Use UTC-normalized epoch for comparison
    if hasattr(d.ts, "timestamp"):
        d_ts = d.ts.timestamp()
    else:
        d_ts = 0.0

    best: ExecutionRecord | None = None
    best_delta = float("inf")
    for candidate in candidates:
        er_ts = _parse_exec_ts(candidate.ts)
        if er_ts is None:
            continue
        delta = abs(er_ts - d_ts)
        if delta < best_delta:
            best_delta = delta
            best = candidate

    if best is not None:
        return best
    logger.debug(
        f"Could not find heuristic match for {d.symbol} {d.action}: "
        f"{len(candidates)} candidates, none with parseable timestamps"
    )
    return None


def _match_to_round_trip(
    symbol: str,
    exec_record: ExecutionRecord | None,
    round_trips: list[dict],
) -> RoundTrip | None:
    """Find the round-trip that contains this execution's entry.

    Matches by symbol + price proximity (relative 0.1% tolerance) AND temporal containment
    (execution timestamp must fall within the round-trip's [opened_at, closed_at] window).
    """
    if exec_record is None:
        return None

    er_ts = _parse_exec_ts(exec_record.ts)

    for rt in round_trips:
        if rt["symbol"] != symbol:
            continue
        entry_price = rt["entry_price"]
        filled_price = exec_record.filled_price
        if entry_price <= 0 or filled_price <= 0:
            continue
        # Relative tolerance: 0.1% = $0.10 on $100, $1.00 on $1000
        if abs(entry_price - filled_price) / entry_price >= 0.001:
            continue
        # Temporal containment check
        if er_ts is not None:
            rt_open = _parse_exec_ts(rt["opened_at"])
            rt_close = _parse_exec_ts(rt["closed_at"])
            if rt_open is not None and rt_close is not None:
                if not (rt_open <= er_ts <= rt_close):
                    continue
        return RoundTrip(**rt)
    return None


def _extract_benchmark_paths(
    ohlc_cache: dict[str, pd.DataFrame],
    outcomes: list[DecisionOutcome],
) -> tuple[list[dict] | None, list[dict] | None]:
    """Extract SPY/QQQ price paths as list[dict] for benchmark comparison."""
    spy_path = None
    qqq_path = None

    if not outcomes:
        return None, None

    earliest = min(o.price_path[0].date for o in outcomes if o.price_path)
    latest = max(o.price_path[-1].date for o in outcomes if o.price_path)

    for bench, name in [("SPY", "vs_spy"), ("QQQ", "vs_qqq")]:
        df = ohlc_cache.get(bench)
        if df is None or df.empty:
            continue
        try:
            mask = (df.index >= pd.Timestamp(earliest)) & (df.index <= pd.Timestamp(latest))
            sliced = df.loc[mask]
            path = [
                {"date": str(getattr(row, "Index", pd.NaT)),
                 "open": float(row.Open), "high": float(row.High),
                 "low": float(row.Low), "close": float(row.Close)}
                for row in sliced.itertuples()
            ]
            if name == "vs_spy":
                spy_path = path
            else:
                qqq_path = path
        except Exception as exc:
            logger.debug(f"Benchmark path extraction failed for {bench}: {exc}")

    return spy_path, qqq_path


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

    Returns:
        List of DecisionOutcome records. The caller should also use the returned
        benchmark paths from _extract_benchmark_paths if needed.
    """
    decisions = journal.read_decisions()
    # F62: include shorts (SELL_SHORT/BUY_TO_COVER) — the match/price-path logic
    # below is direction-agnostic. Excess (attached after the loop) is the part
    # that is direction-aware. HOLD/ADJUST_STOP carry no tradeable outcome.
    buy_sell = [
        (i, d) for i, d in enumerate(decisions)
        if d.action in ("BUY", "SELL", "SELL_SHORT", "BUY_TO_COVER")
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

    # Benchmark data — fetch alongside stock symbols (batched, not separate calls)
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
            if er.decision_index in used_exec:
                er = None
                method = "unmatched"
            else:
                used_exec.add(er.decision_index)

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

    # F62: attach direction-aware benchmark excess so the efficacy layer can
    # aggregate it per lesson / prompt_version (collect_outcomes previously
    # dropped the benchmark paths entirely).
    _attach_excess(outcomes, ohlc_cache)
    return outcomes


def _attach_excess(
    outcomes: list[DecisionOutcome],
    ohlc_cache: dict[str, pd.DataFrame],
) -> None:
    """Set ``outcome.excess`` in place: mean of available SPY/QQQ excess, made
    direction-aware. Entry decisions only — BUY keeps the long-direction excess,
    SELL_SHORT inverts it (a short profits as price falls); exits/HOLD stay None.
    """
    from src.agent.quality.metrics import benchmark_excess

    spy_path, qqq_path = _extract_benchmark_paths(ohlc_cache, outcomes)
    for o in outcomes:
        if o.decision.action not in ("BUY", "SELL_SHORT"):
            continue  # excess is an entry-decision metric
        be = benchmark_excess(o, spy_path, qqq_path)
        vals = [v for v in (be.get("vs_spy"), be.get("vs_qqq")) if v is not None]
        if not vals:
            continue
        base = sum(vals) / len(vals)
        o.excess = -base if o.decision.action == "SELL_SHORT" else base

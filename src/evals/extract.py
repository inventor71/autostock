"""Scenario skeleton extractor: freeze a past (date, symbol) from the records.

Fills everything the operational records can actually reconstruct and marks
the rest ``TODO_MANUAL`` — the records do NOT keep news headlines, fundamentals
or the exact context a past turn saw (turns.jsonl is metadata-only), so those
fixture keys must be authored by hand. Primary enrichment source: the
``positions/<SYM>.md`` Call-vs-Outcome log, which narrates the headlines that
mattered at the time.

Auto-filled:
- held positions / account fixture — from ``equity.jsonl`` (per-day snapshots)
- quote / indicators fixtures — daily bars re-pulled date-pinned and run
  through the SAME tool functions production uses (full parity, no re-derived
  math)
- decisions.jsonl history for the symbol up to the date

Usage:
    python -m src.evals.extract --date 2026-06-08 --symbol AAPL \
        --turn-type intraday [--workspace workspace] [--out evals/scenarios/...]
"""

from __future__ import annotations

import argparse
import json
from datetime import date as date_t
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.agent.tools import market

from src.evals.scenario import Expectation, Scenario, save_scenario

TODO = "TODO_MANUAL"


class _PinnedProvider:
    """get_bars view over a pre-fetched frame, so market.quote/indicators run
    unmodified against history (parity with the live tool path)."""

    def __init__(self, bars: pd.DataFrame):
        self._bars = bars

    def get_bars(self, symbol: str, limit: int = 100, **_) -> pd.DataFrame:
        return self._bars.tail(limit)


def _default_bar_fetcher(symbol: str, asof: date_t) -> pd.DataFrame:
    from src.data.providers.yfinance_provider import YFinanceProvider

    return YFinanceProvider().get_bars(
        symbol,
        start=datetime.combine(asof - timedelta(days=300), datetime.min.time()),
        end=datetime.combine(asof + timedelta(days=1), datetime.min.time()),
        limit=10_000,
    )


def _equity_snapshot(workspace: Path, asof: date_t) -> dict | None:
    """Last equity.jsonl line on/before the date (per-day book snapshot)."""
    path = workspace / "equity.jsonl"
    if not path.exists():
        return None
    best = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            if row.get("date") and row["date"] <= asof.isoformat():
                best = row
        except json.JSONDecodeError:
            continue
    return best


def _decisions_history(workspace: Path, symbol: str, asof: date_t, cap: int = 20) -> list[dict]:
    path = workspace / "decisions.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("symbol", "").upper() != symbol:
            continue
        ts = str(row.get("ts", ""))
        if ts[:10] and ts[:10] <= asof.isoformat():
            rows.append(row)
    return rows[-cap:]


def extract_skeleton(
    *,
    workspace: str | Path,
    symbol: str,
    asof: date_t,
    turn_type: str,
    bar_fetcher=None,
) -> Scenario:
    workspace = Path(workspace)
    symbol = symbol.upper()
    fetch = bar_fetcher or _default_bar_fetcher

    tool_fixtures: dict = {}
    prices: dict[str, float] = {}

    bars = fetch(symbol, asof)
    if bars is not None and not bars.empty:
        pinned = _PinnedProvider(bars)
        tool_fixtures["quote"] = {symbol: market.quote(symbol, pinned)}
        tool_fixtures["indicators"] = {symbol: market.indicators(symbol, pinned)}
        prices[symbol] = float(bars["close"].iloc[-1])

    held: dict = {}
    snap = _equity_snapshot(workspace, asof)
    if snap:
        positions = []
        for p in snap.get("positions", []):
            sym = p["symbol"].upper()
            held[sym] = {"qty": p["qty"], "avg_entry_price": p["avg"], "side": "long"}
            prices.setdefault(sym, p["price"])
            unreal = (p["price"] / p["avg"] - 1) * 100 if p["avg"] else None
            positions.append({
                "symbol": sym, "side": "long", "qty": p["qty"],
                "avg_entry": p["avg"], "price": p["price"],
                "unrealized_pnl": p.get("pnl"),
                "unrealized_pct": round(unreal, 2) if unreal is not None else None,
                "market_value": round(p["qty"] * p["price"], 2),
            })
        tool_fixtures["account"] = {"_": {
            "equity": snap.get("equity"), "cash": snap.get("cash"),
            "invested": snap.get("invested"),
            "invested_pct": snap.get("invested_pct"),
            "position_count": len(positions), "positions": positions,
            "open_orders": [{"note": f"{TODO}: resting stop/target legs as of {asof}"}],
        }}

    # Not persisted anywhere — must be authored (see positions/<SYM>.md
    # Call-vs-Outcome narration for what mattered that day).
    tool_fixtures["news"] = {symbol: {"symbol": symbol, "news": [
        {"title": f"{TODO}: headline as of {asof}", "publisher": TODO,
         "published_at": f"{asof}T00:00:00+00:00", "link": "", "sentiment": 0.0},
    ]}}

    workspace_files: dict[str, str] = {}
    thesis = workspace / "positions" / f"{symbol}.md"
    if thesis.exists():
        workspace_files[f"positions/{symbol}.md"] = (
            f"<!-- {TODO}: trim Call-vs-Outcome rows AFTER {asof} — the agent "
            "must not see the future -->\n" + thesis.read_text(encoding="utf-8"))
    lessons = workspace / "lessons.md"
    if lessons.exists():
        workspace_files["lessons.md"] = (
            f"<!-- {TODO}: remove lessons learned AFTER {asof} -->\n"
            + lessons.read_text(encoding="utf-8"))

    return Scenario(
        id=f"{symbol.lower()}-{asof.isoformat()}-{turn_type}",
        turn_type=turn_type,  # type: ignore[arg-type]
        origin=f"{TODO}: which lesson/real event does this freeze?",
        description=f"extracted skeleton for {symbol} as of {asof}",
        universe=sorted({symbol, *held}),
        brief=f"{TODO}: the intraday/wake brief text the turn should see",
        tool_fixtures=tool_fixtures,
        workspace_files=workspace_files,
        decisions_history=_decisions_history(workspace, symbol, asof),
        held=held,
        prices=prices,
        expectation=Expectation(no_churn=True, note=f"{TODO}: define expected behavior"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.evals.extract")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD (the frozen day)")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--turn-type", required=True,
                        choices=["intraday", "wake", "eod"])
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--out", default=None,
                        help="output path (default: evals/scenarios/<turn>/<id>.json)")
    args = parser.parse_args(argv)

    asof = date_t.fromisoformat(args.date)
    scenario = extract_skeleton(
        workspace=args.workspace, symbol=args.symbol,
        asof=asof, turn_type=args.turn_type,
    )
    out = Path(args.out) if args.out else (
        Path("evals/scenarios") / args.turn_type / f"{scenario.id}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    save_scenario(scenario, out)
    todo_count = json.dumps(scenario.model_dump(mode="json")).count(TODO)
    print(f"wrote {out} ({todo_count} {TODO} markers to enrich)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

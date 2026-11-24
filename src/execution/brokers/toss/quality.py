"""Keep executable quotes distinct from bounded, indicative portfolio marks."""
from __future__ import annotations

from datetime import datetime

from src.execution.brokers.toss.broker import _time

VALUATION_MAX_AGE = 120.0
MAX_STALE_VALUE_PCT = 1.0


def quote_quality(state: dict, now: datetime, fresh: set[str], errors: dict) -> dict:
    symbols = set(state["positions"]) | set(state["initial"]["positions"])
    symbols |= {r["order"]["symbol"] for r in state["orders"].values()
                if r["status"] in {"open", "partial"}}
    stale = (symbols - fresh) | (set(errors) & symbols)
    ages = {}
    unavailable = set(errors) & symbols
    for symbol in sorted(symbols):
        mark = state["marks"].get(symbol, {})
        source = mark.get("source_at")
        age = (now - _time(source)).total_seconds() if source else None
        ages[symbol] = age
        if age is None or not 0 <= age <= VALUATION_MAX_AGE:
            unavailable.add(symbol)
    coverage = {}
    for name, positions, cash in (("strategy", state["positions"], state["cash"]),
                                 ("hold", state["initial"]["positions"], state["initial"]["cash"])):
        values = {s: p["qty"] * state["marks"][s]["price"] for s, p in positions.items()}
        total = cash + sum(values.values())
        stale_value = sum(v for s, v in values.items() if s in stale)
        coverage[name] = max(0.0, 100 * (1 - stale_value / total)) if total > 0 else 0.0
    usable = not unavailable and min(coverage.values()) >= 100 - MAX_STALE_VALUE_PCT
    return {
        "as_of": now.isoformat(),
        "status": "fresh" if not stale and usable else ("indicative" if usable else "unavailable"),
        "all_quotes_fresh": not stale and not unavailable,
        "valuation_usable": usable,
        "fresh_value_pct": coverage,
        "quote_age_seconds": ages,
        "indicative_symbols": sorted(stale - unavailable),
        "unavailable_symbols": sorted(unavailable),
        "execution_max_age_seconds": state["execution"]["max_quote_age"],
        "valuation_max_age_seconds": VALUATION_MAX_AGE,
        "max_indicative_value_pct": MAX_STALE_VALUE_PCT,
    }


def record_session(state: dict, now: datetime, report: dict) -> None:
    """Only fully fresh observations define comparable session returns."""
    from src.execution.brokers.toss.costs import ET

    day = now.astimezone(ET).date().isoformat()
    session = state.setdefault("session_performance", {}).setdefault(day, {
        "start_at": now.isoformat(), "start_equity_usd": report["equity_usd"],
        "start_hold_equity_usd": report["hold_equity_usd"],
        "start_fill_count": report["fill_count"], "observations": 0,
    })
    session.update(end_at=now.isoformat(), end_equity_usd=report["equity_usd"],
                   end_hold_equity_usd=report["hold_equity_usd"])
    session["observations"] += 1
    session["net_return_pct"] = 100 * (report["equity_usd"] / session["start_equity_usd"] - 1)
    session["hold_return_pct"] = 100 * (report["hold_equity_usd"] / session["start_hold_equity_usd"] - 1)
    session["excess_return_pct_points"] = session["net_return_pct"] - session["hold_return_pct"]

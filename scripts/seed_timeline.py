#!/usr/bin/env python3
"""Seed a workspace with synthetic timeline sessions for one or more PAST ET dates.

Reusable operator-console timeline seeder: writes turns.jsonl + decisions.jsonl +
human_directives.jsonl so the timeline bar, its turn/intervention overlays, and the
historical decision breakdown can be exercised without a live trading day.

Each seeded day is **deterministically varied** from a base template (whole-day time shift +
per-turn jitter, some turns/interventions dropped, confidences perturbed), keyed off the date —
so consecutive days look distinct yet reproduce identically on re-run. Decisions are emitted
WITHOUT turn_id and timestamped INSIDE their turn's window, so the TUI's historical correlation
path (mirrors src/agent/steering/runtime.py `_correlate_turn`) is exercised and each decision
resolves to the right turn. Timestamps are tz-aware ET so the daemon/TUI group them into one ET
session regardless of host/container timezone.

Usage (inside the docker-verify `attach` container — its workspace is a named volume):
    python scripts/seed_timeline.py --workspace /app/workspace --date 2026-06-02 --days 6
    # seeds 2026-06-02 back through 2026-05-28, each day different. --overwrite truncates first.

Defaults: --date = yesterday ET, --days 1, append (use --overwrite to replace the files).
After seeding, open `attach`, press [ < ] to a seeded date, click a turn marker (header +
summary + decision rows) or a ◆ intervention (overlay opens).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Base template. Each turn: (type, "HH:MM" ET, [(symbol, action, confidence, reason, min_offset)]).
# min_offset = minutes after the turn's start for that decision (kept small so it stays in-window).
TURN_TEMPLATES: list[tuple[str, str, list[tuple[str, str, float, str, int]]]] = [
    ("research", "08:00", [
        ("WMT", "BUY", 0.70, "breakout above multi-day range", 1),
        ("AAPL", "HOLD", 0.60, "thesis intact; no add", 2),
        ("MSFT", "HOLD", 0.70, "wait for a pullback to support", 3),
    ]),
    ("intraday", "09:35", [("AAPL", "BUY", 0.72, "momentum confirmed off the open", 1)]),
    ("intraday", "11:10", [("NVDA", "BUY", 0.66, "semis leading; relative strength", 2)]),
    ("intraday", "12:00", [("TSLA", "ADJUST_STOP", 0.80, "raise stop to breakeven after +1R", 1)]),
    ("wake", "14:45", []),  # fill-driven wake, no decision
    ("intraday", "15:45", [
        ("TSLA", "SELL", 0.70, "take profit into the close", 1),
        ("META", "HOLD", 0.60, "hold the winner overnight", 2),
    ]),
    ("eod", "16:20", []),
]

# (command, symbol, "HH:MM" ET, outcome, detail)
INTERVENTION_TEMPLATES: list[tuple[str, str, str, str, str]] = [
    ("buy", "AAPL", "09:40", "executed", "10sh @ market, ATR bracket attached"),
    ("sell", "TSLA", "13:15", "executed", "50% of position, 7sh @ 431.00"),
]

TURN_TYPE_COST = {"research": 2.4, "intraday": 0.3, "wake": 0.4, "eod": 1.1}
SUMMARY_HINT = {
    "research": "Research scan", "intraday": "Intraday check",
    "wake": "Wake: abnormal move / new fill", "eod": "EOD review",
}


def _hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _hhmm(t: int) -> str:
    t = max(4 * 60, min(t, 19 * 60 + 59))  # clamp inside a plausible trading window
    return f"{t // 60:02d}:{t % 60:02d}"


def _ts(date: str, minutes: int) -> str:
    y, mo, d = map(int, date.split("-"))
    return datetime(y, mo, d, minutes // 60, minutes % 60, tzinfo=ET).isoformat(timespec="seconds")


def _day_rng(date: str) -> random.Random:
    """Deterministic per-date RNG (stable across runs)."""
    return random.Random(int(hashlib.sha1(date.encode()).hexdigest()[:12], 16))


def build_day(date: str) -> tuple[list[dict], list[dict], list[dict]]:
    rng = _day_rng(date)
    day_shift = rng.randint(-30, 35)  # whole-day shift → each date sits at different times

    turns: list[dict] = []
    decisions: list[dict] = []
    # Keep research(first) + eod(last) anchors; others may drop for variety.
    for idx, (ttype, base, decs) in enumerate(TURN_TEMPLATES):
        anchor = ttype in ("research", "eod")
        if not anchor and rng.random() < 0.25:
            continue
        start_min = _hm(base) + day_shift + rng.randint(-8, 8)
        kept_decs = [d for d in decs if rng.random() > 0.15] if decs else []
        tid = f"{date.replace('-', '')[-4:]}{idx}"  # e.g. 06020, 06021, ...
        turns.append({
            "_min": start_min, "turn_id": tid, "turn_type": ttype, "num_decisions": len(kept_decs),
            "cost_usd": round(TURN_TYPE_COST.get(ttype, 0.3) * rng.uniform(0.7, 1.3), 2),
            "summary": f"{SUMMARY_HINT.get(ttype, ttype)}: "
                       + (", ".join(f"{a} {s}({c:.2f})" for s, a, c, _r, _o in kept_decs) or "no decisions"),
        })
        for sym, action, conf, reason, off in kept_decs:
            decisions.append({
                "_min": start_min + off, "symbol": sym, "action": action,
                "confidence": round(min(0.95, max(0.3, conf + rng.uniform(-0.08, 0.08))), 2),
                "reason": reason,
            })

    turns.sort(key=lambda r: r["_min"])
    decisions.sort(key=lambda r: r["_min"])

    turn_recs = [{
        "turn_id": t["turn_id"],
        "started_at": _ts(date, t["_min"]), "ts": _ts(date, t["_min"]),
        "date": date, "et_date": date, "turn_type": t["turn_type"], "model": "test",
        "num_decisions": t["num_decisions"], "cost_usd": t["cost_usd"],
        "duration_ms": 2000 + t["num_decisions"] * 1500, "summary": t["summary"], "health": "ok",
    } for t in turns]
    # decisions.jsonl: NO turn_id / et_date — the TUI reconstructs both for historical dates.
    dec_recs = [{
        "ts": _ts(date, d["_min"]), "symbol": d["symbol"], "action": d["action"],
        "confidence": d["confidence"], "reason": d["reason"], "source": "agent",
    } for d in decisions]

    iv_recs: list[dict] = []
    for verb, sym, base, outcome, detail in INTERVENTION_TEMPLATES:
        if rng.random() < 0.25:
            continue
        m = _hm(base) + day_shift + rng.randint(-10, 10)
        iv_recs.append({
            "ts": _ts(date, m), "et_date": date, "kind": "trade",
            "command": verb, "args": {"symbol": sym}, "outcome": outcome, "detail": detail,
        })
    iv_recs.sort(key=lambda r: r["ts"])
    return turn_recs, dec_recs, iv_recs


def main() -> None:
    yesterday = (datetime.now(ET).date() - timedelta(days=1)).isoformat()
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=yesterday, help="latest ET date to seed YYYY-MM-DD (default: yesterday ET)")
    ap.add_argument("--days", type=int, default=1, help="number of consecutive past days to seed back from --date")
    ap.add_argument("--workspace", default="workspace", help="journal root (default: ./workspace; attach: /app/workspace)")
    ap.add_argument("--overwrite", action="store_true", help="truncate the jsonl files first (default: append)")
    args = ap.parse_args()

    root = Path(args.workspace)
    root.mkdir(parents=True, exist_ok=True)

    anchor = datetime.strptime(args.date, "%Y-%m-%d").date()
    dates = [(anchor - timedelta(days=i)).isoformat() for i in range(max(1, args.days))]

    all_turns: list[dict] = []
    all_decs: list[dict] = []
    all_ivs: list[dict] = []
    for d in dates:
        tr, dr, ir = build_day(d)
        all_turns += tr
        all_decs += dr
        all_ivs += ir

    mode = "w" if args.overwrite else "a"
    for name, recs in (("turns.jsonl", all_turns), ("decisions.jsonl", all_decs), ("human_directives.jsonl", all_ivs)):
        with (root / name).open(mode, encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r) + "\n")

    print(f"seeded {len(dates)} day(s) [{dates[-1]} .. {dates[0]}] ({'overwrite' if args.overwrite else 'append'}) -> {root}")
    print(f"  {len(all_turns)} turns, {len(all_decs)} decisions, {len(all_ivs)} interventions (varied per date)")
    print(f"  open attach, press [ < ] to a seeded date; each date now has different marker times.")


if __name__ == "__main__":
    main()

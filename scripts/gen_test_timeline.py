#!/usr/bin/env python3
"""F25: seed a workspace with synthetic turns + interventions to exercise the
timeline bar (3 market regions, edge-clamped off-window markers, human markers).

Usage:
    python scripts/gen_test_timeline.py [--date YYYY-MM-DD] [--workspace DIR]

Defaults: --date = today (ET),  --workspace = ./workspace.
The timestamps are tz-aware ET so the daemon/TUI group them into one ET session
regardless of the host timezone. Run it, then open the console and navigate to
the date (it is "Today" if you used the default) to see the markers.

Window is the regular session ±... (06:45–18:45 ET): the 05:00 and 19:30 turns
land outside it and should render as edge arrows (‹ / ›)."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# (turn_id, type, "HH:MM" ET, cost, num_decisions, summary, health)
TURNS = [
    ("R0", "research", "05:00", 0.00, 0, "Research: pre-dawn scan (off-window left)", "ok"),
    ("R1", "research", "08:00", 2.46, 5, "Research: HOLD AAPL(0.6), HOLD MSFT(0.7), BUY WMT(0.7), +2 more", "ok"),
    ("I1", "intraday", "09:35", 0.31, 1, "Intraday: BUY AAPL(0.7)", "ok"),
    ("I2", "intraday", "10:30", 0.28, 0, "Intraday: no decisions", "ok"),
    ("W1", "wake", "11:12", 0.46, 0, "Wake: AAPL abnormal move +2.1% (vol spike)", "ok"),
    ("I3", "intraday", "12:00", 0.30, 1, "Intraday: ADJUST_STOP TSLA(0.8)", "ok"),
    ("I4", "intraday", "14:00", 0.33, 0, "Intraday: no decisions", "ok"),
    ("W2", "wake", "14:45", 0.41, 1, "Wake: new fill META 5sh @ 634.42", "ok"),
    ("I5", "intraday", "15:45", 0.29, 2, "Intraday: SELL TSLA(0.7), HOLD META(0.6)", "ok"),
    ("E1", "eod", "16:20", 1.12, 0, "EOD review: 3 round-trips, +$71 day P&L", "ok"),
    ("X1", "intraday", "19:30", 0.05, 0, "Intraday: after-hours check (off-window right)", "error"),
]

# (command, symbol, "HH:MM" ET, outcome, detail)
INTERVENTIONS = [
    ("buy", "AAPL", "09:40", "executed", "10sh @ market, ATR bracket attached"),
    ("sell", "TSLA", "13:15", "executed", "50% of position, 7sh @ 431.00"),
    ("flatten", "META", "15:50", "executed", "closed 5sh, cancelled resting OCO first"),
    ("cancel", "AAPL", "10:05", "applied", "cancelled resting protective orders"),
]


# --- F34: markers that DELIBERATELY land on the PRE/OPEN/AFT label glyphs ---------
# The inline region label sits ONE column in from each region's left edge. For the
# default 12h regular-centered window those left edges are: window-left 06:45 (PRE),
# regular-open 09:30 (OPEN), regular-close 16:00 (AFT) — all ET. The number of minutes
# per timeline column depends on the terminal width, so a single marker easily misses
# the 3-4 label columns (this is why the old seed didn't overlap). A small cluster at
# +5/+8/+11/+14 min after each boundary reliably covers the label glyph columns across
# all realistic timeline widths (~80-450 cols), so a marker always sits BEHIND a letter.
# Verify (F34): the PRE/OPEN/AFT letters stay fully visible on top, and clicking the
# letter cell still opens the hidden marker's popup (turn probes → turn popup; the
# intervention probe → human-intervention popup, which wins the click when stacked).
def _shift_hhmm(hhmm: str, mins: int) -> str:
    h, m = map(int, hhmm.split(":"))
    total = h * 60 + m + mins
    return f"{total // 60:02d}:{total % 60:02d}"


_LABEL_ANCHORS = [("PRE", "06:45"), ("OPEN", "09:30"), ("AFT", "16:00")]
for _name, _anchor in _LABEL_ANCHORS:
    for _i, _off in enumerate((5, 8, 11, 14)):
        TURNS.append((
            f"L{_name}{_i}", "intraday", _shift_hhmm(_anchor, _off),
            0.10, 0, f"F34 label-overlap probe ({_name} +{_off}m)", "ok",
        ))
    # one human-intervention probe per label (distinct glyph/color; tests the
    # intervention forwarding path + its priority over a turn at the same column)
    INTERVENTIONS.append((
        "buy", "NVDA", _shift_hhmm(_anchor, 8), "executed",
        f"F34 label-overlap probe ({_name})",
    ))


def _ts(date: str, hhmm: str) -> datetime:
    y, m, d = map(int, date.split("-"))
    h, mi = map(int, hhmm.split(":"))
    return datetime(y, m, d, h, mi, tzinfo=ET)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(ET).date().isoformat(),
                    help="ET trading date YYYY-MM-DD (default: today ET)")
    ap.add_argument("--workspace", default="workspace",
                    help="journal root to write into (default: ./workspace)")
    ap.add_argument("--append", action="store_true",
                    help="append instead of overwriting the jsonl files")
    args = ap.parse_args()

    root = Path(args.workspace)
    root.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.append else "w"

    turns_path = root / "turns.jsonl"
    with turns_path.open(mode, encoding="utf-8") as fh:
        for tid, ttype, hhmm, cost, ndec, summary, health in TURNS:
            ts = _ts(args.date, hhmm)
            rec = {
                "turn_id": tid,
                "started_at": ts.isoformat(timespec="seconds"),
                "ts": ts.isoformat(timespec="seconds"),
                "date": ts.date().isoformat(),
                "et_date": args.date,
                "turn_type": ttype,
                "model": "test",
                "num_decisions": ndec,
                "cost_usd": cost,
                "duration_ms": 2000 + ndec * 1500,
                "summary": summary,
                "health": health,
            }
            fh.write(json.dumps(rec) + "\n")

    iv_path = root / "human_directives.jsonl"
    with iv_path.open(mode, encoding="utf-8") as fh:
        for verb, sym, hhmm, outcome, detail in INTERVENTIONS:
            ts = _ts(args.date, hhmm)
            rec = {
                "ts": ts.isoformat(timespec="seconds"),
                "kind": "trade",
                "command": verb,
                "args": {"symbol": sym},
                "outcome": outcome,
                "detail": detail,
            }
            fh.write(json.dumps(rec) + "\n")

    print(f"wrote {len(TURNS)} turns -> {turns_path}")
    print(f"wrote {len(INTERVENTIONS)} interventions -> {iv_path}")
    print(f"ET session date: {args.date}  (navigate the timeline to this date)")


if __name__ == "__main__":
    main()

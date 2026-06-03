"""CLI inspection tool for early-session event data.

Usage::

    python -m early_session inspect --date 2026-06-03
    python -m early_session inspect --date 2026-06-03 --symbol AAPL
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _workspace_root() -> Path:
    """Resolve the workspace root (where workspace/ lives)."""
    # The early_session module lives at src/early_session/; go up 2 levels.
    return Path(__file__).resolve().parent.parent.parent


def cmd_inspect(args) -> None:
    """Print event index and optionally time-series for a date."""
    root = _workspace_root() / "workspace" / "early_session" / args.date
    index_path = root / "_index.jsonl"

    if not index_path.exists():
        print(f"No events found for {args.date}")
        return

    print(f"=== Early-Session Events: {args.date} ===\n")
    events = []
    for line in index_path.read_text().strip().splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    for ev in events:
        marker = " ▲" if ev["direction"] == "surge" else " ▼"
        print(
            f"  {ev['symbol']:6s} {ev['detected_at']:20s} "
            f"{ev['direction']:5s} {ev['trigger_pct']:+6.2f}%{marker}"
        )

    if args.symbol:
        print(f"\n--- Time-series for {args.symbol} ---")
        # Find the data file
        for ev in events:
            if ev["symbol"] == args.symbol:
                data_path = root / ev["data_file"]
                if data_path.exists():
                    for line in data_path.read_text().strip().splitlines():
                        if not line.strip():
                            continue
                        bar = json.loads(line)
                        direction = ""
                        if "o" in bar and "c" in bar:
                            direction = "▲" if bar["c"] > bar["o"] else "▼"
                        print(
                            f"  {bar.get('t','?'):20s} "
                            f"O:{bar.get('o','?'):8.2f} H:{bar.get('h','?'):8.2f} "
                            f"L:{bar.get('l','?'):8.2f} C:{bar.get('c','?'):8.2f} "
                            f"V:{bar.get('v',0):>8.0f} {direction}"
                        )
                break

    print(f"\n{len(events)} event(s) total")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Early-session signal inspection tool"
    )
    sub = parser.add_subparsers(dest="command")

    insp = sub.add_parser("inspect", help="View events for a date")
    insp.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")
    insp.add_argument("--symbol", default=None, help="Filter by symbol")

    args = parser.parse_args()
    if args.command == "inspect":
        cmd_inspect(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

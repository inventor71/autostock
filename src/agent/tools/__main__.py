"""CLI entry: ``python -m src.agent.tools <cmd> [args]`` -> JSON on stdout.

Wires the real yfinance-backed providers to the tool functions in ``market``.
The PM agent invokes these via Bash; everything is read-only.
"""

from __future__ import annotations

import argparse
import json
import sys

from src.agent.tools import market


def _provider():
    from src.data.providers.yfinance_provider import YFinanceProvider
    return YFinanceProvider()


def _universe() -> list[str]:
    from config.config import get_settings
    return list(get_settings().trading.symbols)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.agent.tools")
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in ("quote", "indicators", "fundamentals", "news"):
        p = sub.add_parser(name)
        p.add_argument("symbol")
    sub.choices["news"].add_argument("--limit", type=int, default=8)

    sc = sub.add_parser("scoreboard")
    sc.add_argument(
        "--symbols", nargs="*", default=None,
        help="Symbols to scan (default: the configured universe).",
    )

    args = parser.parse_args(argv)

    if args.cmd == "quote":
        out = market.quote(args.symbol, _provider())
    elif args.cmd == "indicators":
        out = market.indicators(args.symbol, _provider())
    elif args.cmd == "fundamentals":
        out = market.fundamentals(args.symbol)
    elif args.cmd == "news":
        out = market.news(args.symbol, limit=args.limit)
    elif args.cmd == "scoreboard":
        symbols = args.symbols or _universe()
        out = market.scoreboard(symbols, _provider())
    else:  # pragma: no cover - argparse enforces choices
        parser.error(f"unknown command: {args.cmd}")

    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

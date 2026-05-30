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


def _broker():
    from config.config import get_settings
    from src.execution.brokers.alpaca_broker import AlpacaBroker

    settings = get_settings()
    return AlpacaBroker(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key,
        paper=settings.broker.paper,
    )


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

    sub.add_parser("account")  # no args: live broker snapshot

    # F3: structured intraday watch-triggers (the sole writer of watch.jsonl, BR-6.1).
    wp = sub.add_parser("watch")
    wsub = wp.add_subparsers(dest="watch_cmd", required=True)
    ws_set = wsub.add_parser("set")
    ws_set.add_argument("symbol")
    ws_set.add_argument("condition",
                        choices=["price_above", "price_below", "close_above", "close_below"])
    ws_set.add_argument("level", type=float)
    ws_set.add_argument("--intent", default="")
    ws_set.add_argument("--until", default=None, help="ET expiry date YYYY-MM-DD")
    ws_set.add_argument("--thesis", default=None)
    ws_clear = wsub.add_parser("clear")
    ws_clear.add_argument("id")
    wsub.add_parser("list")

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
    elif args.cmd == "account":
        out = market.account(_broker())
    elif args.cmd == "watch":
        from src.agent.intraday.watch_store import WatchStore
        from src.agent.journal import Journal

        store = WatchStore(Journal().root)
        if args.watch_cmd == "set":
            t = store.set(args.symbol, args.condition, args.level, intent=args.intent,
                          valid_until=args.until, thesis_ref=args.thesis)
            out = {"set": t.model_dump(mode="json")}
        elif args.watch_cmd == "clear":
            store.clear(args.id)
            out = {"cleared": args.id}
        else:  # list
            out = {"active": [t.model_dump(mode="json") for t in store.active()]}
    else:  # pragma: no cover - argparse enforces choices
        parser.error(f"unknown command: {args.cmd}")

    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

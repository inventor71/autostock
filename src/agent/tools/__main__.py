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
        secret_key=settings.alpaca_api_secret,
        paper=settings.broker.paper,
    )


def _universe() -> list[str]:
    from config.config import get_settings
    return list(get_settings().trading.symbols)


def _signal_collector():
    from src.signals.collector import SignalCollector

    # Wire held positions so the tools surface imminent earnings for held names
    # that sit OUTSIDE the tradeable universe too (matches the daemon push path).
    # The broker is built lazily inside the callable; collect()'s held lookup is
    # best-effort, so a missing-key/broker failure degrades to held=[].
    def _held() -> list[str]:
        return sorted(_broker().get_portfolio_state().positions.keys())

    return SignalCollector.from_settings(price_provider=_provider(), held_provider=_held)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.agent.tools")
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in ("quote", "indicators", "fundamentals", "news",
                  "earnings", "insider", "analyst_upgrades", "institutional",
                  "short_data"):
        p = sub.add_parser(name)
        p.add_argument("symbol")
    sub.choices["news"].add_argument("--limit", type=int, default=8)

    sub.add_parser("macro")

    lp = sub.add_parser("lesson")
    lsub = lp.add_subparsers(dest="lesson_cmd", required=True)
    la = lsub.add_parser("add")
    la.add_argument("--category", default="other")
    la.add_argument("--signal", default="")
    la.add_argument("--outcome", default="")
    la.add_argument("--takeaway", required=True)

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

    # F47: surge stock tools
    sl = sub.add_parser("surge-list")
    sl.add_argument("--date", default=None, help="Trading date YYYY-MM-DD (default: today)")

    sa = sub.add_parser("surge-analyze")
    sa.add_argument("symbol")
    sa.add_argument("date")
    sa.add_argument("cause")
    sa.add_argument("leading_indicators")
    sa.add_argument("information_gap")

    # F61: market-signal tools
    sub.add_parser("movers")  # no args: scan universe + bellwethers
    rt = sub.add_parser("readthrough")
    rt.add_argument("symbol")
    ec = sub.add_parser("earnings_calendar")
    ec.add_argument("--days", type=int, default=None, help="Horizon override (default: config)")

    args = parser.parse_args(argv)

    if args.cmd == "quote":
        out = market.quote(args.symbol, _provider())
    elif args.cmd == "indicators":
        out = market.indicators(args.symbol, _provider())
    elif args.cmd == "fundamentals":
        out = market.fundamentals(args.symbol)
    elif args.cmd == "short_data":
        out = market.short_data(args.symbol)
    elif args.cmd == "news":
        out = market.news(args.symbol, limit=args.limit)
    elif args.cmd == "scoreboard":
        symbols = args.symbols or _universe()
        out = market.scoreboard(symbols, _provider())
    elif args.cmd == "earnings":
        out = market.earnings(args.symbol)
    elif args.cmd == "insider":
        out = market.insider(args.symbol)
    elif args.cmd == "analyst_upgrades":
        out = market.analyst_upgrades(args.symbol)
    elif args.cmd == "institutional":
        out = market.institutional(args.symbol)
    elif args.cmd == "macro":
        out = market.macro()
    elif args.cmd == "lesson":
        import os
        from src.agent.journal import Journal, LessonRecord

        root = os.environ.get("AGENT_JOURNAL_ROOT") or Journal().root
        journal = Journal(root)
        record = LessonRecord(
            lesson_id=journal.next_lesson_id(),
            category=args.category,
            signal_used=args.signal,
            outcome=args.outcome,
            takeaway=args.takeaway,
        )
        journal.append_lesson_record(record)
        out = {"added": record.model_dump()}
    elif args.cmd == "account":
        out = market.account(_broker())
    elif args.cmd == "watch":
        import os

        from src.agent.intraday.watch_store import WatchStore
        from src.agent.journal import Journal

        # Write to the SAME journal root the daemon's WatchStore reads. The daemon
        # exports its root as AGENT_JOURNAL_ROOT when it spawns the agent, so a
        # non-default workspace doesn't split writer/reader (review #5).
        root = os.environ.get("AGENT_JOURNAL_ROOT") or Journal().root
        store = WatchStore(root)
        if args.watch_cmd == "set":
            t = store.set(args.symbol, args.condition, args.level, intent=args.intent,
                          valid_until=args.until, thesis_ref=args.thesis)
            out = {"set": t.model_dump(mode="json")}
        elif args.watch_cmd == "clear":
            store.clear(args.id)
            out = {"cleared": args.id}
        else:  # list
            out = {"active": [t.model_dump(mode="json") for t in store.active()]}
    elif args.cmd == "movers":
        out = market.movers(_signal_collector())
    elif args.cmd == "readthrough":
        from config.config import get_settings
        from src.signals.peer_map import PeerMap
        from src.signals.settings import SignalsConfig

        cfg = SignalsConfig.from_settings(get_settings().signals)
        out = market.readthrough(args.symbol, PeerMap.from_config(cfg.peer_groups), _universe())
    elif args.cmd == "earnings_calendar":
        out = market.earnings_calendar(_signal_collector(), days=args.days)
    elif args.cmd == "surge-list":
        out = market.surge_list(args.date)
    elif args.cmd == "surge-analyze":
        out = market.surge_analyze(
            args.symbol, args.date, args.cause,
            args.leading_indicators, args.information_gap,
        )
    else:  # pragma: no cover - argparse enforces choices
        parser.error(f"unknown command: {args.cmd}")

    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
    from src.universe.factory import resolve_universe
    return resolve_universe(get_settings())


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
    # F62: situational recall keys (F65). Tag the conditions a lesson depends on
    # at creation time, else the lesson is born untagged and recall can't key on it.
    la.add_argument("--regime", default="", help="market regime this lesson depends on")
    la.add_argument("--sector", default=None, help="sector this lesson is about (optional)")

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
    ic = sub.add_parser("ipo_calendar")
    ic.add_argument("--days", type=int, default=None, help="IPO horizon override (default: config)")
    sub.add_parser("disclosed_holdings")  # no args: institutional 13F (incl. SHORT side)

    # F88: agent self-authored long-horizon triggers. Writes to the SAME triggers
    # store the daemon's TriggerEvaluator reads (workspace/triggers/), so the
    # filesystem is the cross-process channel — no live daemon connection needed.
    tg = sub.add_parser("trigger")
    tgsub = tg.add_subparsers(dest="trigger_cmd", required=True)
    tg_reg = tgsub.add_parser("register")
    tg_reg.add_argument("--id", required=True)
    tg_reg.add_argument("--thesis", required=True)
    tg_reg.add_argument("--cadence", choices=["hourly", "daily"], default="hourly")
    tg_reg.add_argument("--ttl-days", type=float, required=True, dest="ttl_days")
    tg_reg.add_argument("--predicate-file", required=True, dest="predicate_file",
                        help="path to a file containing should_fire(ctx) source")
    tg_reg.add_argument("--sources-json", default="[]", dest="sources_json",
                        help='JSON list of source refs, e.g. '
                             '[{"kind":"signal","name":"macro"},{"kind":"webfetch","url":"https://..."}]')
    tg_reg.add_argument("--primary-symbol", default=None, dest="primary_symbol")
    tg_reg.add_argument("--no-entry-inducing", action="store_true", dest="no_entry_inducing",
                        help="mark a non-entry-inducing trigger (fires even when entries halted)")
    tg_insp = tgsub.add_parser("inspect")
    tg_insp.add_argument("id")
    tg_can = tgsub.add_parser("cancel")
    tg_can.add_argument("id")
    tgsub.add_parser("list")

    args = parser.parse_args(argv)

    # F74: eval fixture interception — a market command under
    # AUTOSTOCK_TOOLS_FIXTURE_DIR is answered from the scenario fixture before
    # any data wiring runs, so an eval turn can never touch live data. A
    # missing fixture key yields an explicit fixture_missing error object.
    from src.agent.tools.fixtures import (
        MARKET_COMMANDS,
        FixtureStore,
        RecordingStore,
        command_key,
    )

    fixture = FixtureStore.from_env()
    recorder = RecordingStore.from_env() if fixture is None else None
    if fixture is not None and RecordingStore.from_env() is not None:
        sys.stderr.write("tools: fixture mode active; record dir ignored\n")
    if fixture is not None and args.cmd in MARKET_COMMANDS:
        json.dump(fixture.get(args.cmd, command_key(args)), sys.stdout,
                  indent=2, default=str)
        sys.stdout.write("\n")
        return 0

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
        from src.agent.logs import screening

        symbols = args.symbols or _universe()
        out = market.scoreboard(symbols, _provider())
        # F72: persist the latest FULL-universe scan for the operator's
        # /screening view. A partial --symbols run must not clobber the day's
        # record (critic #1). Fail-honest — a save failure never sinks the scan.
        if args.symbols is None:
            screening.record_scan(out)
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
            regime=args.regime,
            sector=args.sector,
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
    elif args.cmd == "trigger":
        import os
        from datetime import datetime, timedelta, timezone
        from pathlib import Path

        from src.agent.journal import Journal
        from src.agent.triggers import SourceRef, TriggerSpec, TriggerStore
        from src.agent.triggers.store import TriggerError

        # Same root the daemon's TriggerEvaluator reads (AGENT_JOURNAL_ROOT export),
        # so a non-default workspace never splits writer/reader (cf. the watch tool).
        root = os.environ.get("AGENT_JOURNAL_ROOT") or Journal().root
        store = TriggerStore(Path(root) / "triggers")
        if args.trigger_cmd == "register":
            try:
                predicate_src = Path(args.predicate_file).read_text()
                sources = [SourceRef(**s) for s in json.loads(args.sources_json)]
                spec = TriggerSpec(
                    id=args.id, thesis=args.thesis, cadence=args.cadence,
                    expires=datetime.now(timezone.utc) + timedelta(days=args.ttl_days),
                    sources=sources, primary_symbol=args.primary_symbol,
                    entry_inducing=not args.no_entry_inducing,
                )
                store.register(spec, predicate_src)
                out = {"ok": True, "id": spec.id}
            except TriggerError as e:
                out = {"ok": False, "error": str(e), "violations": [str(v) for v in e.violations]}
            except Exception as e:  # malformed spec/sources/file → structured error, not a traceback
                out = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        elif args.trigger_cmd == "list":
            out = {"triggers": [s.model_dump(mode="json") for s in store.list()]}
        elif args.trigger_cmd == "inspect":
            try:
                out = store.inspect(args.id).model_dump(mode="json")
            except TriggerError as e:
                out = {"ok": False, "error": str(e)}
        else:  # cancel
            out = {"cancelled": store.cancel(args.id)}
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
    elif args.cmd == "ipo_calendar":
        out = market.ipo_calendar(_signal_collector(), days=args.days)
    elif args.cmd == "disclosed_holdings":
        out = market.disclosed_holdings(_signal_collector())
    elif args.cmd == "surge-list":
        out = market.surge_list(args.date)
    elif args.cmd == "surge-analyze":
        out = market.surge_analyze(
            args.symbol, args.date, args.cause,
            args.leading_indicators, args.information_gap,
        )
    else:  # pragma: no cover - argparse enforces choices
        parser.error(f"unknown command: {args.cmd}")

    if recorder is not None and args.cmd in MARKET_COMMANDS:
        try:
            recorder.save(args.cmd, command_key(args), out)
        except Exception as exc:  # capture aid must never sink a live tool call
            sys.stderr.write(f"tools: record failed ({exc})\n")

    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

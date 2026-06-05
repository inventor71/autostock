"""Tier 2 — on-demand agent-judgement eval harness (F61, FR-5a / NFR-7).

Feeds a historical scenario's signal brief to the real agent and prints its
read-through judgement. This **calls the LLM (token cost)** and is therefore a
manual, explicit entry point — it lives outside ``tests/`` and is never run by
``pytest``/CI (the default test run stays at zero tokens).

Usage:
    python -m src.signals.eval_readthrough S1
    python -m src.signals.eval_readthrough --list
    python -m src.signals.eval_readthrough S1 --brief-only   # no LLM, just render

The deterministic brief assembly reuses the exact pure core the production path
uses, so what the agent sees here matches a real turn.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from src.signals.brief import assemble_brief, to_prompt_text
from src.signals.earnings_cal import select_imminent_earnings
from src.signals.movers import detect_movers
from src.signals.peer_map import PeerMap
from src.signals.readthrough import build_readthrough
from src.signals.records import EarningsRow, MoverRow
from src.signals.settings import SignalsConfig

_SCENARIO_DIR = Path(__file__).resolve().parents[2] / "tests" / "signals" / "scenarios"


def _load_scenario(scenario_id: str) -> dict:
    path = _SCENARIO_DIR / f"{scenario_id}.json"
    if not path.exists():
        raise SystemExit(f"scenario not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_brief_text(scenario: dict, *, today: date | None = None) -> str:
    """Build the prompt brief text from a scenario fixture (deterministic, no LLM)."""
    today = today or date.today()
    cfg = SignalsConfig(**scenario.get("config", {}))
    peer_map = PeerMap.from_config(scenario.get("peer_groups", {}))
    universe = {s.upper() for s in scenario.get("universe", [])}
    held = {s.upper() for s in scenario.get("held", [])}

    rows = [MoverRow(**r) for r in scenario.get("rows", [])]
    movers = detect_movers(
        rows, price_pct=cfg.price_pct, vol_ratio=cfg.vol_ratio,
        universe=universe, require=cfg.require, max_movers=cfg.max_movers,
    )
    alerts = build_readthrough(
        movers, peer_map, universe,
        min_trigger_pct=cfg.readthrough_min_pct, max_peers=cfg.max_peers,
    )
    news = {k.upper(): v for k, v in scenario.get("news", {}).items()}
    for a in alerts:
        if a.trigger_symbol in news:
            a.cause_hint = news[a.trigger_symbol][:120]

    earnings_rows = [EarningsRow(**e) for e in scenario.get("earnings", [])]
    imminent = select_imminent_earnings(
        earnings_rows, universe, held, peer_map,
        horizon_days=cfg.earnings_horizon_days, today=today,
    )
    brief = assemble_brief(movers, alerts, imminent)
    return to_prompt_text(brief)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.signals.eval_readthrough")
    parser.add_argument("scenario", nargs="?", help="scenario id (e.g. S1)")
    parser.add_argument("--list", action="store_true", help="list available scenarios")
    parser.add_argument("--brief-only", action="store_true",
                        help="render the brief only — do NOT call the LLM")
    args = parser.parse_args(argv)

    if args.list or not args.scenario:
        scenarios = sorted(p.stem for p in _SCENARIO_DIR.glob("*.json"))
        print("Available scenarios:", ", ".join(scenarios))
        return 0

    scenario = _load_scenario(args.scenario)
    brief_text = build_brief_text(scenario)
    print("=" * 70)
    print(f"Scenario {args.scenario}: {scenario.get('description', '')}")
    print("=" * 70)
    print(brief_text or "(empty brief)")
    print("=" * 70)

    if args.brief_only:
        return 0

    # --- LLM judgement (token cost) ---
    from src.agent.session import AgentSession

    prompt = (
        f"{brief_text}\n\n"
        "You are a PM trading agent. Based ONLY on the market signal brief above, "
        "state for each read-through alert whether you would actually act on it and "
        "why (one line each). Be decisive and concise. Do not place any orders."
    )
    print("Running agent judgement (this calls the LLM)...\n")
    session = AgentSession()
    result = session.run_turn(prompt)
    print(getattr(result, "result", result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

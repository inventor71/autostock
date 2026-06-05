"""Shared helpers for the market-signal (F61) tests."""

from __future__ import annotations

from datetime import date

from src.signals.brief import assemble_brief
from src.signals.earnings_cal import select_imminent_earnings
from src.signals.movers import detect_movers
from src.signals.peer_map import PeerMap
from src.signals.readthrough import build_readthrough
from src.signals.records import EarningsRow, MarketSignalBrief, MoverRow
from src.signals.settings import SignalsConfig


def build_scenario_brief(
    scenario: dict, *, today: date | None = None
) -> MarketSignalBrief:
    """Run the exact pure pipeline a real turn uses over a scenario fixture.

    Deterministic, no I/O — this is what the Tier-1 scenario corpus asserts on.
    """
    today = today or date(2026, 6, 5)
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
    return assemble_brief(movers, alerts, imminent, as_of=None)

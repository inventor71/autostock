"""Guards on the SHIPPED config seed (F61) — not a fixture.

The scenario corpus uses self-contained fixture peer maps, which can pass even
if config/settings.yaml is misconfigured. These tests load the REAL
``signals:`` block so a regression in the shipped peer map / bellwether list is
caught (e.g. a bellwether ETF that belongs to no group can never trigger
read-through — the original gap this guards against).
"""

from __future__ import annotations

import pytest

from config.config import get_settings
from src.signals.peer_map import PeerMap
from src.signals.settings import SignalsConfig


@pytest.fixture(scope="module")
def cfg() -> SignalsConfig:
    return SignalsConfig.from_settings(get_settings().signals)


@pytest.fixture(scope="module")
def peer_map(cfg) -> PeerMap:
    return PeerMap.from_config(cfg.peer_groups)


@pytest.fixture(scope="module")
def universe() -> set[str]:
    return {s.upper() for s in get_settings().trading.symbols}


def test_every_bellwether_reads_through_to_a_universe_name(cfg, peer_map, universe):
    """The core guard: every bellwether watchlist entry must propagate to >=1
    tradeable name, else it can be a mover but never a read-through trigger."""
    orphans = []
    for etf in cfg.bellwether_watchlist:
        universe_peers = [p for p in peer_map.peers_of(etf) if p in universe]
        if not universe_peers:
            orphans.append(etf)
    assert not orphans, (
        f"bellwether(s) with no universe peer (read-through inert): {orphans}. "
        "Add each to a peer_group in config/settings.yaml signals.peer_groups."
    )


def test_avgo_reads_through_to_semiconductor_peers(peer_map, universe):
    peers = {p for p in peer_map.peers_of("AVGO") if p in universe}
    assert {"NVDA", "AMD", "MRVL"} <= peers


def test_xle_bellwether_reads_through_to_energy(peer_map, universe):
    peers = {p for p in peer_map.peers_of("XLE") if p in universe}
    assert {"XOM", "CVX"} <= peers


def test_smh_bellwether_reads_through_to_semis(peer_map, universe):
    peers = {p for p in peer_map.peers_of("SMH") if p in universe}
    assert {"NVDA", "AVGO"} <= peers


def test_bellwether_etfs_are_not_tradeable(cfg, universe):
    """Bellwethers are signal-only; they must not leak into the tradeable universe."""
    assert not (set(cfg.bellwether_watchlist) & universe)

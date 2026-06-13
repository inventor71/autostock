"""Tests for the F61 agent tools (movers / readthrough / earnings_calendar)."""

from __future__ import annotations

from datetime import date, datetime

from src.agent.tools import market
from src.signals.peer_map import PeerMap
from src.signals.records import (
    ImminentEarnings,
    ImminentIpo,
    MarketSignalBrief,
    Mover,
    ReadThroughAlert,
)


class _FakeCollector:
    def __init__(self, brief):
        self._brief = brief
        self.config = type("C", (), {"earnings_horizon_days": 2, "ipo_horizon_days": 5})()
        self.last_horizon_days = "unset"
        self.last_ipo_horizon_days = "unset"

    def collect(self, *, horizon_days=None, ipo_horizon_days=None):
        self.last_horizon_days = horizon_days
        self.last_ipo_horizon_days = ipo_horizon_days
        return self._brief


def _brief():
    return MarketSignalBrief(
        as_of=datetime(2026, 6, 5, 9, 0),
        movers=[Mover(symbol="AVGO", change_pct=-15.0, direction="down",
                      in_universe=True, qualified_by=["price"])],
        readthrough_alerts=[ReadThroughAlert(trigger_symbol="AVGO", trigger_change_pct=-15.0,
                                             affected_peers=["NVDA"], groups=["semis"])],
        imminent_earnings=[ImminentEarnings(symbol="NVDA", earnings_date=date(2026, 6, 6),
                                            when="amc")],
        imminent_ipos=[ImminentIpo(name="SpaceX", symbol="SPCX", ipo_date=date(2026, 6, 6),
                                   status="priced", est_value=75e9, exchange="NASDAQ")],
        degraded_sources=["earnings:finnhub"],
    )


def test_movers_tool():
    out = market.movers(_FakeCollector(_brief()))
    assert [m["symbol"] for m in out["movers"]] == ["AVGO"]
    assert out["readthrough_alerts"][0]["trigger_symbol"] == "AVGO"
    assert out["degraded_sources"] == ["earnings:finnhub"]
    assert out["as_of"].startswith("2026-06-05")


def test_readthrough_tool_pure_lookup():
    pm = PeerMap.from_config({"semis": ["AVGO", "NVDA", "AMD"], "x": ["AVGO", "ZZZ"]})
    out = market.readthrough("avgo", pm, universe=["NVDA", "AMD"])
    assert out["symbol"] == "AVGO"
    assert set(out["peers_universe"]) == {"NVDA", "AMD"}
    assert "ZZZ" in out["peers_all"] and "ZZZ" not in out["peers_universe"]
    assert set(out["groups"]) == {"semis", "x"}


def test_earnings_calendar_tool():
    out = market.earnings_calendar(_FakeCollector(_brief()))
    assert [e["symbol"] for e in out["imminent_earnings"]] == ["NVDA"]


def test_earnings_calendar_days_override_passed_through_not_mutated():
    collector = _FakeCollector(_brief())
    market.earnings_calendar(collector, days=5)
    # days is passed to collect(), NOT written onto the shared config
    assert collector.last_horizon_days == 5
    assert collector.config.earnings_horizon_days == 2


def test_movers_does_not_override_horizon():
    collector = _FakeCollector(_brief())
    market.movers(collector)
    assert collector.last_horizon_days is None


def test_ipo_calendar_tool():
    out = market.ipo_calendar(_FakeCollector(_brief()))
    assert [i["symbol"] for i in out["imminent_ipos"]] == ["SPCX"]
    assert out["imminent_ipos"][0]["name"] == "SpaceX"
    assert out["degraded_sources"] == ["earnings:finnhub"]


def test_ipo_calendar_days_override_passed_through_not_mutated():
    collector = _FakeCollector(_brief())
    market.ipo_calendar(collector, days=10)
    # days flows to collect() as ipo_horizon_days, NOT onto the shared config
    assert collector.last_ipo_horizon_days == 10
    assert collector.last_horizon_days is None
    assert collector.config.ipo_horizon_days == 5

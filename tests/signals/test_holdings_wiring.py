"""Holdings wiring (F81): refresher fail-honest, universe-overlay integration,
collector cache-read step. All fail-honest, no network.
"""

from __future__ import annotations

from datetime import date

from src.signals.holdings.records import HoldingRow, HoldingsSnapshot
from src.signals.holdings.refresher import HoldingsRefresher
from src.signals.holdings.store import read_snapshots, write_snapshot
from src.signals.settings import SignalsConfig
from src.universe.factory import _holdings_overlay


# --------------------------------------------------------------------------- #
# Refresher — fail-honest
# --------------------------------------------------------------------------- #
class _GoodProvider:
    source_id = "sec_13f:1"
    manager_name = "SA LP"

    def fetch_snapshot(self):
        return HoldingsSnapshot(
            source_id=self.source_id, manager_name=self.manager_name,
            as_of=date(2026, 3, 31),
            rows=[HoldingRow(ticker="CLSK", side="LONG", weight=1.0)])


class _BadProvider:
    source_id = "sec_13f:bad"
    manager_name = "Boom"

    def fetch_snapshot(self):
        raise RuntimeError("SEC down")


def test_refresher_writes_good_skips_bad(tmp_path):
    HoldingsRefresher(providers=[_GoodProvider(), _BadProvider()], root=tmp_path).refresh_tick()
    got = read_snapshots(root=tmp_path)
    assert [s.source_id for s in got] == ["sec_13f:1"]  # bad provider degraded, not fatal


def test_refresher_never_raises_when_all_fail(tmp_path):
    HoldingsRefresher(providers=[_BadProvider()], root=tmp_path).refresh_tick()  # must not raise
    assert read_snapshots(root=tmp_path) == []


def test_refresher_empty_providers_is_noop(tmp_path):
    HoldingsRefresher(providers=[], root=tmp_path).refresh_tick()
    assert read_snapshots(root=tmp_path) == []


# --------------------------------------------------------------------------- #
# Universe overlay integration (factory._holdings_overlay) — fail-honest + gating
# --------------------------------------------------------------------------- #
class _Risk:
    def __init__(self, shorting):
        self.shorting_enabled = shorting


class _Settings:
    def __init__(self, *, enabled, shorting=False, providers=None):
        self.signals = {
            "disclosed_holdings": {
                "enabled": enabled,
                "max_age_days": 135,
                "providers": providers if providers is not None else [
                    {"type": "sec_13f", "cik": "0002045724", "overlay": True},
                ],
            }
        }
        self.risk = _Risk(shorting)


def _seed_cache(root):
    write_snapshot(
        HoldingsSnapshot(
            source_id="sec_13f:0002045724", manager_name="SA LP", as_of=date(2026, 3, 31),
            rows=[
                HoldingRow(ticker="CLSK", side="LONG", weight=0.5),
                HoldingRow(ticker="NVDA", side="SHORT", weight=0.5),
            ]),
        root=root)


def test_factory_overlay_long_only_default(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_JOURNAL_ROOT", str(tmp_path))
    _seed_cache(tmp_path)
    out = _holdings_overlay(_Settings(enabled=True, shorting=False))
    assert out == ["CLSK"]


def test_factory_overlay_includes_short_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_JOURNAL_ROOT", str(tmp_path))
    _seed_cache(tmp_path)
    out = _holdings_overlay(_Settings(enabled=True, shorting=True))
    assert out == ["CLSK", "NVDA"]


def test_factory_overlay_disabled_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_JOURNAL_ROOT", str(tmp_path))
    _seed_cache(tmp_path)
    assert _holdings_overlay(_Settings(enabled=False)) == []


def test_factory_overlay_brief_only_source_excluded(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_JOURNAL_ROOT", str(tmp_path))
    _seed_cache(tmp_path)
    settings = _Settings(
        enabled=True, shorting=True,
        providers=[{"type": "sec_13f", "cik": "0002045724", "overlay": False}])
    assert _holdings_overlay(settings) == []  # overlay:false → brief-only


def test_factory_overlay_failsafe_on_garbage_settings():
    # Any error inside must yield [] so the universe never fails to resolve.
    class Broken:
        signals = {"disclosed_holdings": {"enabled": True, "providers": "not-a-list"}}
        risk = _Risk(False)

    assert _holdings_overlay(Broken()) == []


# --------------------------------------------------------------------------- #
# Collector cache-read step — fail-honest, no HTTP
# --------------------------------------------------------------------------- #
def _collector(tmp_path):
    from src.signals.collector import SignalCollector

    cfg = SignalsConfig.from_settings(
        {"disclosed_holdings": {"enabled": True, "max_age_days": 135}})
    return SignalCollector(config=cfg, universe=[], price_provider=None, root=tmp_path)


def test_collector_reads_holdings_highlights(tmp_path):
    _seed_cache(tmp_path)
    degraded: list[str] = []
    out = _collector(tmp_path)._disclosed_holdings(date(2026, 4, 1), degraded)
    assert len(out) == 1 and out[0].source_id == "sec_13f:0002045724"
    assert "CLSK" in out[0].long_top and "NVDA" in out[0].short_top
    assert degraded == []


def test_collector_disabled_returns_empty(tmp_path):
    from src.signals.collector import SignalCollector

    cfg = SignalsConfig.from_settings({"disclosed_holdings": {"enabled": False}})
    col = SignalCollector(config=cfg, universe=[], price_provider=None, root=tmp_path)
    assert col._disclosed_holdings(date(2026, 4, 1), []) == []


def test_collector_no_cache_is_silent(tmp_path):
    degraded: list[str] = []
    assert _collector(tmp_path)._disclosed_holdings(date(2026, 4, 1), degraded) == []
    assert degraded == []  # absence is not a degraded source

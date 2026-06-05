"""Unit tests for universe providers (F30) — no network."""

from __future__ import annotations

import json

import pytest

from src.universe.base import BaseUniverseProvider, UniverseError
from src.universe.kr_provider import KRUniverseProvider


class StubProvider(BaseUniverseProvider):
    market = "test"

    def __init__(self, base, **kw):
        super().__init__(**kw)
        self._base = base

    def _fetch_base(self):
        if isinstance(self._base, Exception):
            raise self._base
        return self._base


def test_base_union_dedup_sorted(tmp_path):
    p = StubProvider(["AAA", "bbb", "AAA"], snapshot_path=tmp_path / "s.json",
                     themes={"semis": ["ccc", "AAA"]}, enabled_themes=["semis"])
    assert p.get_symbols() == ["AAA", "BBB", "CCC"]


def test_disabled_theme_excluded(tmp_path):
    p = StubProvider(["AAA"], snapshot_path=tmp_path / "s.json",
                     themes={"semis": ["CCC"]}, enabled_themes=[])
    assert p.get_symbols() == ["AAA"]


def test_undefined_enabled_theme_ignored(tmp_path):
    p = StubProvider(["AAA"], snapshot_path=tmp_path / "s.json", enabled_themes=["nope"])
    assert p.get_symbols() == ["AAA"]


def test_snapshot_written_and_used_on_failure(tmp_path):
    snap = tmp_path / "s.json"
    StubProvider(["AAA", "BBB"], snapshot_path=snap).get_symbols()  # writes snapshot
    assert json.loads(snap.read_text()) == ["AAA", "BBB"]
    # next provider: fetch raises -> falls back to snapshot
    p2 = StubProvider(RuntimeError("boom"), snapshot_path=snap)
    assert p2.get_symbols() == ["AAA", "BBB"]


def test_empty_everything_is_fail_closed(tmp_path):
    p = StubProvider([], snapshot_path=tmp_path / "missing.json")
    with pytest.raises(UniverseError):
        p.get_symbols()


def test_cache_avoids_refetch(tmp_path):
    p = StubProvider(["AAA"], snapshot_path=tmp_path / "s.json")
    p.get_symbols()
    p._base = ["ZZZ"]  # would change result if refetched
    assert p.get_symbols() == ["AAA"]  # served from cache


class FakeKis:
    def __init__(self, kospi, kosdaq):
        self._map = {"2001": kospi, "1001": kosdaq}

    def get(self, path, tr, params):
        codes = self._map.get(params["FID_INPUT_ISCD"], [])
        return {"rt_cd": "0", "output": [{"mksc_shrn_iscd": c} for c in codes]}


def test_kr_provider_unions_kospi_and_kosdaq(tmp_path):
    kis = FakeKis(kospi=["005930", "000660"], kosdaq=["247540"])
    p = KRUniverseProvider(kis, snapshot_path=tmp_path / "kr.json",
                           kospi_n=200, kosdaq_n=150)
    p._min_base = lambda: 1  # don't trip the sanity floor on a tiny fake
    assert p.get_symbols() == ["000660", "005930", "247540"]

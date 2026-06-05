"""Unit tests for mover detection (F61, R1)."""

from src.signals.movers import detect_movers
from src.signals.records import MoverRow

_UNI = {"AAA", "BBB", "CCC"}


def _rows(data):
    return [MoverRow(symbol=s, change_pct=c, volume_ratio=v, close=p) for s, c, v, p in data]


def test_price_threshold():
    rows = _rows([("AAA", 6.0, 1.0, 10.0), ("BBB", 4.9, 1.0, 10.0)])
    out = detect_movers(rows, price_pct=5.0, vol_ratio=2.0, universe=_UNI)
    assert {m.symbol for m in out} == {"AAA"}
    assert out[0].qualified_by == ["price"]
    assert out[0].direction == "up"


def test_volume_threshold_alone_qualifies():
    rows = _rows([("AAA", 1.0, 2.5, 10.0)])
    out = detect_movers(rows, price_pct=5.0, vol_ratio=2.0, universe=_UNI)
    assert out and out[0].qualified_by == ["volume"]


def test_require_both():
    rows = _rows([("AAA", 6.0, 1.0, 10.0), ("BBB", 6.0, 2.5, 10.0)])
    out = detect_movers(rows, price_pct=5.0, vol_ratio=2.0, universe=_UNI, require="both")
    assert {m.symbol for m in out} == {"BBB"}


def test_sorted_by_abs_change_and_capped():
    rows = _rows([("AAA", 6.0, 1.0, 10.0), ("BBB", -12.0, 1.0, 10.0), ("CCC", 8.0, 1.0, 10.0)])
    out = detect_movers(rows, price_pct=5.0, vol_ratio=2.0, universe=_UNI, max_movers=2)
    assert [m.symbol for m in out] == ["BBB", "CCC"]


def test_in_universe_flag():
    rows = _rows([("AAA", 9.0, 1.0, 10.0), ("XLE", 9.0, 1.0, 90.0)])
    out = detect_movers(rows, price_pct=5.0, vol_ratio=2.0, universe=_UNI)
    flags = {m.symbol: m.in_universe for m in out}
    assert flags == {"AAA": True, "XLE": False}


def test_none_change_skipped():
    rows = [MoverRow(symbol="AAA", change_pct=None, volume_ratio=5.0)]
    assert detect_movers(rows, price_pct=5.0, vol_ratio=2.0, universe=_UNI) == []


def test_negative_direction():
    rows = _rows([("AAA", -7.0, 1.0, 10.0)])
    out = detect_movers(rows, price_pct=5.0, vol_ratio=2.0, universe=_UNI)
    assert out[0].direction == "down"


def test_nan_change_is_skipped():
    # yfinance can return NaN change for halted/stale bars; such a row must not
    # become a "+nan%" mover (and must not slip into read-through as a trigger).
    nan = float("nan")
    rows = [
        MoverRow(symbol="AAA", change_pct=nan, volume_ratio=9.0, close=10.0),  # high vol but NaN chg
        MoverRow(symbol="BBB", change_pct=8.0, volume_ratio=1.0, close=10.0),
    ]
    out = detect_movers(rows, price_pct=5.0, vol_ratio=2.0, universe=_UNI)
    assert {m.symbol for m in out} == {"BBB"}


def test_nan_volume_ratio_ignored_not_qualifying():
    nan = float("nan")
    rows = [MoverRow(symbol="AAA", change_pct=1.0, volume_ratio=nan, close=10.0)]
    out = detect_movers(rows, price_pct=5.0, vol_ratio=2.0, universe=_UNI)
    assert out == []  # small price move + NaN volume → not a mover

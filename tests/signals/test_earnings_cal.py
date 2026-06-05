"""Unit tests for imminent-earnings selection (F61, R3)."""

from datetime import date

from src.signals.earnings_cal import select_imminent_earnings
from src.signals.peer_map import PeerMap
from src.signals.records import EarningsRow

_PM = PeerMap.from_config({"semis": ["NVDA", "AMD", "AVGO"]})
_TODAY = date(2026, 6, 5)


def _rows(data):
    return [EarningsRow(symbol=s, earnings_date=d, when=w) for s, d, w in data]


def test_horizon_filter():
    rows = _rows([
        ("NVDA", date(2026, 6, 6), "amc"),   # in horizon (+1)
        ("AMD", date(2026, 6, 10), "bmo"),   # outside (+5)
        ("AVGO", date(2026, 6, 4), "amc"),   # past
    ])
    out = select_imminent_earnings(rows, {"NVDA", "AMD", "AVGO"}, set(), _PM,
                                   horizon_days=2, today=_TODAY)
    assert {e.symbol for e in out} == {"NVDA"}


def test_universe_or_held_filter():
    rows = _rows([("TSLA", date(2026, 6, 6), "amc")])
    out = select_imminent_earnings(rows, {"NVDA"}, {"TSLA"}, _PM, horizon_days=2, today=_TODAY)
    assert {e.symbol for e in out} == {"TSLA"}
    assert out[0].is_held is True


def test_peer_readthrough_attached():
    rows = _rows([("AVGO", date(2026, 6, 6), "amc")])
    out = select_imminent_earnings(rows, {"AVGO", "NVDA", "AMD"}, set(), _PM,
                                   horizon_days=2, today=_TODAY)
    assert set(out[0].peer_readthrough) == {"NVDA", "AMD"}


def test_sorted_by_date():
    rows = _rows([("AMD", date(2026, 6, 7), "amc"), ("NVDA", date(2026, 6, 6), "amc")])
    out = select_imminent_earnings(rows, {"AMD", "NVDA"}, set(), _PM, horizon_days=5, today=_TODAY)
    assert [e.symbol for e in out] == ["NVDA", "AMD"]

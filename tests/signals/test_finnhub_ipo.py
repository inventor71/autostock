"""FinnhubIpoCalendar source parsing (F78) — defensive, fail-honest.

The endpoint is hit through a monkeypatched ``requests.get``; we assert the parse
of the documented ``/calendar/ipo`` shape (price ranges, size proxy, status map)
and that malformed entries are skipped, not guessed (SECURITY-05).
"""

from __future__ import annotations

from datetime import date

import pytest

from src.signals.sources.finnhub_ipo import FinnhubIpoCalendar, _parse_price_range


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


@pytest.fixture
def patch_get(monkeypatch):
    def _patch(payload, status=200):
        captured = {}

        def fake_get(url, params=None, timeout=None):
            captured["url"] = url
            captured["params"] = params
            return _Resp(payload, status)

        monkeypatch.setattr("requests.get", fake_get)
        return captured

    return _patch


def _cal():
    return FinnhubIpoCalendar("key", http_connect_timeout=1.0, http_read_timeout=1.0)


def test_requires_key():
    with pytest.raises(ValueError):
        FinnhubIpoCalendar("")


def test_parses_documented_shape(patch_get):
    captured = patch_get({"ipoCalendar": [
        {"date": "2026-06-12", "exchange": "NASDAQ Global", "name": "SpaceX",
         "numberOfShares": 556600000, "price": "135.00", "status": "priced",
         "symbol": "SPCX", "totalSharesValue": 75141000000},
    ]})
    rows = _cal().get_calendar(date(2026, 6, 12), date(2026, 6, 17))
    assert captured["params"]["from"] == "2026-06-12"
    assert captured["params"]["token"] == "key"
    assert len(rows) == 1
    r = rows[0]
    assert (r.name, r.symbol, r.status, r.exchange) == ("SpaceX", "SPCX", "priced", "NASDAQ Global")
    assert r.ipo_date == date(2026, 6, 12)
    assert r.shares == 556600000
    assert r.price_low == 135.0 and r.price_high == 135.0
    assert r.est_value == 75141000000


def test_price_range_and_unknown_status(patch_get):
    patch_get({"ipoCalendar": [
        {"date": "2026-06-20", "name": "Range Co", "price": "13.00-15.00",
         "status": "rumored", "symbol": None},
    ]})
    r = _cal().get_calendar(date(2026, 6, 1), date(2026, 6, 30))[0]
    assert (r.price_low, r.price_high) == (13.0, 15.0)
    assert r.status == "unknown"   # unmapped status → unknown, never invented
    assert r.symbol is None


def test_skips_malformed_entries(patch_get):
    patch_get({"ipoCalendar": [
        {"exchange": "NYSE"},                              # no name/date → skip
        {"name": "NoDate"},                                # no date → skip
        {"name": "BadDate", "date": "not-a-date"},         # unparseable date → skip
        "not-a-dict",                                      # wrong shape → skip
        {"name": "Good", "date": "2026-06-15"},            # kept
    ]})
    rows = _cal().get_calendar(date(2026, 6, 1), date(2026, 6, 30))
    assert [r.name for r in rows] == ["Good"]


def test_http_error_raises(patch_get):
    patch_get({}, status=429)
    with pytest.raises(RuntimeError):
        _cal().get_calendar(date(2026, 6, 1), date(2026, 6, 30))


def test_empty_payload(patch_get):
    patch_get({})
    assert _cal().get_calendar(date(2026, 6, 1), date(2026, 6, 30)) == []


def test_parse_price_range_helper():
    assert _parse_price_range("135.00") == (135.0, 135.0)
    assert _parse_price_range("13.00-15.00") == (13.0, 15.0)
    assert _parse_price_range("15.00-13.00") == (13.0, 15.0)  # min/max normalized
    assert _parse_price_range("") == (None, None)
    assert _parse_price_range(None) == (None, None)
    assert _parse_price_range("garbage") == (None, None)

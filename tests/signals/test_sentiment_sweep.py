"""StockTwits source parsing + sweep runner discipline (F77, NFR-1/3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.signals.records import SentimentRecord
from src.signals.sentiment import load_recent
from src.signals.sentiment_sweep import SentimentSweeper, _in_window
from src.signals.settings import SentimentConfig
from src.signals.sources import stocktwits
from src.signals.sources.stocktwits import RateLimited, StocktwitsSource

ET_NOON = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)  # 08:00 ET (in window)

# Abridged real response shape (one bullish, one bearish, one untagged message).
_PAYLOAD = {
    "response": {"status": 200},
    "messages": [
        {"id": 30, "body": "ignored", "user": {"username": "ignored"},
         "entities": {"sentiment": {"basic": "Bullish"}}},
        {"id": 29, "entities": {"sentiment": {"basic": "Bearish"}}},
        {"id": 31, "entities": {"sentiment": None}},
        "not-a-dict",
    ],
}


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else _PAYLOAD

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._payload


class TestStocktwitsSource:
    def test_aggregates_labels_and_latest_id_only(self, monkeypatch):
        monkeypatch.setattr("requests.get", lambda url, headers=None, timeout=None: _Resp())
        rec = StocktwitsSource().fetch_symbol("nvda")
        assert rec.symbol == "NVDA"
        assert (rec.bullish_n, rec.bearish_n, rec.untagged_n) == (1, 1, 1)
        assert rec.latest_id == 31
        # nothing but counts/ids survives (no body/username fields exist)
        assert set(rec.model_dump()) == {
            "ts", "symbol", "bullish_n", "bearish_n", "untagged_n", "latest_id"}

    @pytest.mark.parametrize("code", [403, 429])
    def test_rate_limit_raises_ratelimited(self, monkeypatch, code):
        monkeypatch.setattr("requests.get",
                            lambda url, headers=None, timeout=None: _Resp(status_code=code))
        with pytest.raises(RateLimited):
            StocktwitsSource().fetch_symbol("NVDA")

    def test_http_error_raises_normally(self, monkeypatch):
        monkeypatch.setattr("requests.get",
                            lambda url, headers=None, timeout=None: _Resp(status_code=500))
        with pytest.raises(RuntimeError):
            StocktwitsSource().fetch_symbol("NVDA")


class _FakeSource:
    """Scripted per-symbol outcomes: SentimentRecord | Exception."""

    def __init__(self, script):
        self.script = script
        self.calls: list[str] = []

    def fetch_symbol(self, symbol):
        self.calls.append(symbol)
        out = self.script[symbol]
        if isinstance(out, Exception):
            raise out
        return out


def _rec(symbol):
    return SentimentRecord(ts=ET_NOON, symbol=symbol,
                           bullish_n=3, bearish_n=1, untagged_n=0)


def _cfg(**kw):
    base = dict(enabled=True, sweep_minutes=60, window_et=("04:00", "20:00"),
                request_gap_s=0.0, hourly_budget=150, baseline_days=5)
    base.update(kw)
    return SentimentConfig(**base)


def _sweeper(source, cfg, root, universe=("NVDA", "AMD", "MU")):
    return SentimentSweeper(source=source, universe=list(universe), cfg=cfg,
                            root=root, now_fn=lambda: ET_NOON)


class TestSweeper:
    def test_happy_path_persists_all(self, tmp_path):
        src = _FakeSource({s: _rec(s) for s in ("NVDA", "AMD", "MU")})
        _sweeper(src, _cfg(), tmp_path).sweep_tick()
        history = load_recent(tmp_path, days=1, now=ET_NOON)
        assert set(history) == {"NVDA", "AMD", "MU"}

    def test_symbol_failure_skipped_others_collected(self, tmp_path):
        src = _FakeSource({"NVDA": _rec("NVDA"), "AMD": RuntimeError("boom"),
                           "MU": _rec("MU")})
        _sweeper(src, _cfg(), tmp_path).sweep_tick()
        assert set(load_recent(tmp_path, days=1, now=ET_NOON)) == {"NVDA", "MU"}

    def test_rate_limited_aborts_but_persists_partial(self, tmp_path):
        src = _FakeSource({"NVDA": _rec("NVDA"), "AMD": RateLimited("429"),
                           "MU": _rec("MU")})
        _sweeper(src, _cfg(), tmp_path).sweep_tick()
        # aborted at AMD: MU never requested, NVDA still persisted
        assert src.calls == ["NVDA", "AMD"]
        assert set(load_recent(tmp_path, days=1, now=ET_NOON)) == {"NVDA"}

    def test_budget_caps_requests(self, tmp_path):
        src = _FakeSource({s: _rec(s) for s in ("NVDA", "AMD", "MU")})
        _sweeper(src, _cfg(hourly_budget=2), tmp_path).sweep_tick()
        assert len(src.calls) == 2  # acceptance #4: never exceeds the budget

    def test_outside_window_is_noop(self, tmp_path):
        src = _FakeSource({})
        sweeper = SentimentSweeper(
            source=src, universe=["NVDA"], cfg=_cfg(), root=tmp_path,
            now_fn=lambda: datetime(2026, 6, 13, 6, 0, tzinfo=timezone.utc))  # 02:00 ET
        sweeper.sweep_tick()
        assert src.calls == []

    def test_disabled_is_noop(self, tmp_path):
        src = _FakeSource({})
        _sweeper(src, _cfg(enabled=False), tmp_path).sweep_tick()
        assert src.calls == []

    def test_any_exception_is_absorbed(self, tmp_path):
        class _Bomb:
            def fetch_symbol(self, symbol):
                raise SystemError("scheduler must survive")
        _sweeper(_Bomb(), _cfg(), tmp_path).sweep_tick()  # must not raise


class TestWindow:
    def test_in_window_boundaries(self):
        win = ("04:00", "20:00")
        et = lambda h, m: datetime(2026, 6, 12, h, m)
        assert _in_window(et(4, 0), win)
        assert _in_window(et(20, 0), win)
        assert not _in_window(et(3, 59), win)
        assert not _in_window(et(20, 1), win)

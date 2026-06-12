"""F14: daemon-wedge resilience — HTTP timeout injection, BarCache peek/prefetch,
and the WakeDetector detect-first latch (no synchronous fetch on the 5s tick).

These are self-contained (don't touch the network); they exercise exactly the
behaviors the F14 critic rounds pinned down.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.agent.intraday import wake as wake_mod
from src.agent.intraday.abnormal import AbnormalConfig
from src.agent.intraday.bars import BarCache
from src.agent.intraday.records import AbnormalMoveSignal
from src.agent.intraday.wake import WakeDetector
from src.execution.brokers.session_timeout import install_session_timeout


# --------------------------------------------------------------------------- #
# A — HTTP timeout injection
# --------------------------------------------------------------------------- #
class _FakeSession:
    def __init__(self):
        self.calls = []

    def request(self, *args, **kwargs):
        self.calls.append(kwargs.get("timeout", "MISSING"))
        return "ok"


class _FakeClient:
    def __init__(self):
        self._session = _FakeSession()


def test_install_session_timeout_injects_default():
    c = _FakeClient()
    install_session_timeout(c, connect=3.0, read=5.0)
    c._session.request("GET", "/x")
    assert c._session.calls == [(3.0, 5.0)]


def test_install_session_timeout_honors_caller_timeout():
    c = _FakeClient()
    install_session_timeout(c, connect=3.0, read=5.0)
    c._session.request("GET", "/x", timeout=99)
    assert c._session.calls == [99]


def test_install_session_timeout_idempotent():
    c = _FakeClient()
    install_session_timeout(c)
    first = c._session.request  # wrapped once
    install_session_timeout(c)  # must NOT wrap again
    assert c._session.request is first


def test_install_session_timeout_graceful_when_no_session():
    class NoSession:
        pass

    install_session_timeout(NoSession())  # must not raise


# --------------------------------------------------------------------------- #
# B1 — BarCache peek (cache-only, never fetches) + prefetch warms cache
# --------------------------------------------------------------------------- #
class _CountingProvider:
    def __init__(self, price=100.0, bars=None):
        self.price_calls = 0
        self.bars_calls = 0
        self._price = price
        self._bars = bars if bars is not None else _mk_bars()

    def get_latest_price(self, symbol):
        self.price_calls += 1
        return self._price

    def get_bars(self, symbol, timeframe=None, limit=50):
        self.bars_calls += 1
        return self._bars


def _mk_bars(n=5, close=100.0, vol=1000.0):
    idx = pd.date_range("2026-05-29 09:30", periods=n, freq="5min")
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": vol},
        index=idx,
    )


def test_peek_returns_none_before_prefetch():
    bc = BarCache(_CountingProvider())
    assert bc.peek_price("AAA") is None
    assert bc.peek_bars("AAA") is None


def test_peek_never_fetches():
    p = _CountingProvider()
    bc = BarCache(p)
    bc.peek_price("AAA")
    bc.peek_bars("AAA")
    assert p.price_calls == 0 and p.bars_calls == 0


def test_prefetch_fills_cache_then_peek_hits():
    p = _CountingProvider(price=123.0)
    bc = BarCache(p)
    bc.prefetch(["AAA"])
    assert p.price_calls == 1 and p.bars_calls == 1
    assert bc.peek_price("AAA") == 123.0
    assert bc.peek_bars("AAA") is not None
    # peek after prefetch must not add fetches
    bc.peek_price("AAA")
    assert p.price_calls == 1


# --------------------------------------------------------------------------- #
# B2 — WakeDetector: detect path does ZERO network; latch survives cache-miss
# --------------------------------------------------------------------------- #
class _RunState:
    paused = False
    entries_halted = False


class _State:
    def run_state(self):
        return _RunState()


class _WatchStore:
    def active(self):
        return []


class _ReconcileWorker:
    def trigger(self, *a, **k):
        pass


def _make_detector(bar_cache):
    return WakeDetector(
        snapshot_fn=lambda: {"positions": {"AAA": {}}},
        state=_State(),
        watch_store=_WatchStore(),
        bar_cache=bar_cache,
        reconcile_worker=_ReconcileWorker(),
        wake_runner=lambda events: None,
        config=AbnormalConfig(),
        wake_timeout=120.0,
    )


def test_abnormal_events_does_no_network(monkeypatch):
    monkeypatch.setattr(wake_mod, "detect_abnormal", lambda *a, **k: None)
    p = _CountingProvider()
    bc = BarCache(p)
    bc.prefetch(["AAA"])
    base_price, base_bars = p.price_calls, p.bars_calls
    det = _make_detector(bc)
    snap = {"positions": {"AAA": {}}}
    det._abnormal_events(snap)
    assert p.price_calls == base_price and p.bars_calls == base_bars


def _sig(symbol="AAA", kind="price"):
    return AbnormalMoveSignal(
        symbol=symbol, kind=kind, magnitude=5.0, threshold=1.0, reason="test"
    )


def test_latch_survives_cache_miss(monkeypatch):
    """A latched symbol must NOT re-arm when peek returns None (cache miss) —
    otherwise the next tick double-wakes the same episode (critic R3)."""
    p = _CountingProvider()
    bc = BarCache(p)
    bc.prefetch(["AAA"])
    det = _make_detector(bc)
    snap = {"positions": {"AAA": {}}}

    # 1) abnormal signal -> latch set, one event emitted
    monkeypatch.setattr(wake_mod, "detect_abnormal", lambda *a, **k: _sig())
    ev = det._abnormal_events(snap)
    assert len(ev) == 1 and "AAA" in det._abnormal_fired

    # 2) cache miss (peek None) + no signal -> must KEEP the latch (no re-arm)
    bc._price.clear()
    bc._bars.clear()
    monkeypatch.setattr(wake_mod, "detect_abnormal", lambda *a, **k: None)
    det._abnormal_events(snap)
    assert "AAA" in det._abnormal_fired  # still latched


def test_latch_rearms_only_with_sufficient_data(monkeypatch):
    """Re-arm (discard latch) only when data is present AND no signal."""
    p = _CountingProvider()
    bc = BarCache(p)
    bc.prefetch(["AAA"])
    det = _make_detector(bc)
    snap = {"positions": {"AAA": {}}}

    monkeypatch.setattr(wake_mod, "detect_abnormal", lambda *a, **k: _sig())
    det._abnormal_events(snap)
    assert "AAA" in det._abnormal_fired

    # data present (prefetched) + no signal -> real episode clear -> re-arm
    monkeypatch.setattr(wake_mod, "detect_abnormal", lambda *a, **k: None)
    det._abnormal_events(snap)
    assert "AAA" not in det._abnormal_fired


def test_volume_only_signal_fires_with_price_none(monkeypatch):
    """A volume-abnormal signal must still wake even when price peek is None
    (the `or`-guard bug would have dropped it; detect-first does not)."""
    p = _CountingProvider()
    bc = BarCache(p)
    bc.prefetch(["AAA"])
    bc._price.clear()  # price miss, bars still cached
    det = _make_detector(bc)
    snap = {"positions": {"AAA": {}}}
    monkeypatch.setattr(wake_mod, "detect_abnormal", lambda *a, **k: _sig(kind="volume"))
    ev = det._abnormal_events(snap)
    assert len(ev) == 1 and ev[0].kind == "abnormal_move"

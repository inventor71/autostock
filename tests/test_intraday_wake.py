"""Step 8 — WakeDetector + ReconcileWorker per-kind timers (critic#1/#2/#4)."""

from __future__ import annotations

import time

import pandas as pd

from src.agent.intraday.abnormal import AbnormalConfig
from src.agent.intraday.wake import WakeDetector, classify_watch_entry_inducing
from src.agent.steering.turns import ReconcileWorker, TurnCoordinator


# ---- ReconcileWorker per-kind timers (critic#2) ---------------------------- #
def test_per_kind_timers_do_not_starve_human():
    coord = TurnCoordinator()
    worker = ReconcileWorker(coord, debounce=0.05)
    ran: list[str] = []
    try:
        worker.trigger(lambda: ran.append("human"), kind="reconcile")
        # a burst of wake triggers must NOT cancel the human timer
        for _ in range(10):
            worker.trigger(lambda: ran.append("wake"), kind="wake")
            time.sleep(0.005)
        time.sleep(0.3)
        assert "human" in ran and "wake" in ran
    finally:
        worker.stop()


def test_wake_timeout_passed_through(monkeypatch):
    coord = TurnCoordinator()
    seen = {}
    monkeypatch.setattr(coord, "reconcile_turn",
                        lambda fn, *, timeout=600.0: seen.setdefault("t", timeout) or ("ran", fn()))
    worker = ReconcileWorker(coord, debounce=0.02)
    try:
        worker.trigger(lambda: None, kind="wake", timeout=120.0)
        time.sleep(0.2)
        assert seen["t"] == 120.0
    finally:
        worker.stop()


# ---- WakeDetector ---------------------------------------------------------- #
class _RS:
    def __init__(self, paused=False, entries_halted=False):
        self.paused = paused
        self.entries_halted = entries_halted


class _State:
    def __init__(self, rs):
        self._rs = rs

    def run_state(self):
        return self._rs


class _Bars:
    def __init__(self, price=100.0, bars=None):
        self._price = price
        self._bars = bars

    def get_price(self, s):
        return self._price

    def get_bars(self, s):
        return self._bars


class _Worker:
    def __init__(self):
        self.pending = None
        self.triggers = 0

    def trigger(self, run_fn, *, kind="reconcile", timeout=None):
        self.triggers += 1
        self.pending = run_fn

    def fire(self):
        if self.pending:
            self.pending()
            self.pending = None


def _detector(snap, *, rs=None, bars=None, watch=None, price=100.0):
    captured = []
    worker = _Worker()
    det = WakeDetector(
        snapshot_fn=lambda: snap, state=_State(rs or _RS()),
        watch_store=watch, bar_cache=_Bars(price=price, bars=bars),
        reconcile_worker=worker, wake_runner=lambda evs: captured.append(evs),
        config=AbnormalConfig())
    return det, worker, captured


def test_buy_fill_is_new_fill_wake():
    snap = {"positions": {}, "fills": [{"side": "buy", "qty": 5, "symbol": "META", "price": 631.2}]}
    det, worker, captured = _detector(snap)
    det.detect_wakes()
    worker.fire()
    assert [e.kind for e in captured[0]] == ["new_fill"]


def test_sell_fill_is_protective_reassess():
    snap = {"positions": {}, "fills": [{"side": "sell", "qty": 5, "symbol": "AAPL", "price": 98.0}]}
    det, worker, captured = _detector(snap)
    det.detect_wakes()
    worker.fire()
    assert captured[0][0].kind == "protective_reassess"


def test_paused_suppresses_all_wakes():
    snap = {"positions": {}, "fills": [{"side": "buy", "qty": 1, "symbol": "AAPL", "price": 1}]}
    det, worker, captured = _detector(snap, rs=_RS(paused=True))
    det.detect_wakes()
    assert worker.triggers == 0 and captured == []


def test_entries_halted_drops_entry_inducing_only():
    # abnormal upward (entry_inducing) + a new_fill (not). Only the new_fill survives.
    idx = pd.date_range("2026-05-30 09:30", periods=2, freq="5min")
    bars = pd.DataFrame({"open": [100, 100], "high": [101, 101], "low": [99, 99],
                         "close": [100, 100], "volume": [10, 10]}, index=idx)
    snap = {"positions": {"AAPL": {"qty": 1}}, "fills":
            [{"side": "buy", "qty": 1, "symbol": "AAPL", "price": 120}]}
    det, worker, captured = _detector(snap, rs=_RS(entries_halted=True), bars=bars, price=120.0)
    det.detect_wakes()
    worker.fire()
    kinds = {e.kind for e in captured[0]}
    assert "abnormal_move" not in kinds  # entry_inducing dropped under halt
    assert "new_fill" in kinds


def test_coalesce_drains_buffer_at_fire():
    snap = {"positions": {}, "fills": [{"side": "buy", "qty": 1, "symbol": "AAPL", "price": 1}]}
    det, worker, captured = _detector(snap)
    det.detect_wakes()
    det.detect_wakes()  # second tick before fire -> events accumulate in the buffer
    worker.fire()
    assert len(captured) == 1 and len(captured[0]) == 2  # both fills, one turn


class _WT:
    def __init__(self, tid, symbol, condition, level, intent=""):
        self.id = tid
        self.symbol = symbol
        self.condition = condition
        self.level = level
        self.intent = intent


class _Watch:
    def __init__(self, triggers):
        self._t = triggers
        self._fired: set[str] = set()

    def active(self):
        return self._t

    def is_fired(self, tid):
        return tid in self._fired

    def mark_fired(self, tid):
        self._fired.add(tid)


def test_watch_trigger_fires_once():
    watch = _Watch([_WT("w1", "AAPL", "price_above", 99.0)])
    snap = {"positions": {}, "fills": []}
    det, worker, captured = _detector(snap, watch=watch, price=100.0)
    det.detect_wakes()
    worker.fire()
    assert captured[0][0].kind == "watch_trigger"
    # already fired today -> no second wake
    det.detect_wakes()
    assert worker.pending is None and len(captured) == 1


def test_classify_watch_entry_inducing():
    assert classify_watch_entry_inducing(_WT("a", "X", "price_above", 1, "tighten stop")) is False
    assert classify_watch_entry_inducing(_WT("b", "X", "price_above", 1, "add on breakout")) is True
    # ambiguous upside breakout defaults to entry-inducing (halt guarantee)
    assert classify_watch_entry_inducing(_WT("c", "X", "close_above", 1, "")) is True
    assert classify_watch_entry_inducing(_WT("d", "X", "price_below", 1, "")) is False

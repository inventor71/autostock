"""Step 11 — integration: wake path through the REAL ReconcileWorker/TurnCoordinator
+ skip-if-busy while a wake turn is in-flight (V3)."""

from __future__ import annotations

import threading
import time

from src.agent.intraday.wake import WakeDetector
from src.agent.steering.turns import ReconcileWorker, TurnCoordinator


class _RS:
    paused = False
    entries_halted = False


class _State:
    def run_state(self):
        return _RS()


class _Bars:
    def get_price(self, s):
        return 100.0

    def get_bars(self, s):
        return None


def _wait(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_wake_runs_through_real_worker_and_drains_buffer():
    coord = TurnCoordinator()
    worker = ReconcileWorker(coord, debounce=0.05)
    captured: list = []
    snap = {"positions": {}, "fills": [{"side": "buy", "qty": 5, "symbol": "META", "price": 631.2}]}
    det = WakeDetector(snapshot_fn=lambda: snap, state=_State(), watch_store=None,
                       bar_cache=_Bars(), reconcile_worker=worker,
                       wake_runner=lambda evs: captured.append(evs))
    try:
        det.detect_wakes()
        det.detect_wakes()  # both ticks accumulate; one coalesced fire
        assert _wait(lambda: captured)
        assert len(captured) == 1 and len(captured[0]) == 2
    finally:
        worker.stop()


def test_scheduled_turn_skips_while_wake_in_flight():
    coord = TurnCoordinator()
    worker = ReconcileWorker(coord, debounce=0.02)
    in_turn = threading.Event()
    release = threading.Event()

    def _slow_wake(events):
        in_turn.set()
        release.wait(2.0)  # hold the turn_lock (simulates a long LLM wake turn)

    snap = {"positions": {}, "fills": [{"side": "buy", "qty": 1, "symbol": "AAPL", "price": 1}]}
    det = WakeDetector(snapshot_fn=lambda: snap, state=_State(), watch_store=None,
                       bar_cache=_Bars(), reconcile_worker=worker, wake_runner=_slow_wake)
    try:
        det.detect_wakes()
        assert in_turn.wait(2.0)  # wake turn is now in-flight, holding turn_lock
        # a scheduled turn arriving now must SKIP, not queue (C-1/C-2, V3).
        status, _ = coord.try_scheduled_turn(lambda: "ran")
        assert status == "skipped"
    finally:
        release.set()
        worker.stop()

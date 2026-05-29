"""Unit A steering-core -- Step 6: TurnCoordinator + ReconcileWorker."""

from __future__ import annotations

import threading
import time

from src.agent.steering.turns import ReconcileWorker, TurnCoordinator


def test_scheduled_turn_runs_when_free():
    c = TurnCoordinator()
    assert c.try_scheduled_turn(lambda: "ok") == ("ran", "ok")


def test_scheduled_turn_skips_when_in_flight():
    c = TurnCoordinator()
    held = threading.Event()
    release = threading.Event()

    def holder():
        c.try_scheduled_turn(lambda: (held.set(), release.wait(2)))

    t = threading.Thread(target=holder)
    t.start()
    assert held.wait(2)
    # a second scheduled turn while the first is in-flight must SKIP (not queue)
    status, reason = c.try_scheduled_turn(lambda: "should not run")
    assert status == "skipped" and reason == "busy"
    release.set()
    t.join(2)


def test_reconcile_has_priority_over_scheduled():
    c = TurnCoordinator()
    held = threading.Event()
    release = threading.Event()

    # occupy the lock with a scheduled turn
    t_hold = threading.Thread(target=lambda: c.try_scheduled_turn(
        lambda: (held.set(), release.wait(2))))
    t_hold.start()
    assert held.wait(2)

    # a reconcile starts waiting for the lock (blocked)
    recon_done = threading.Event()
    t_recon = threading.Thread(target=lambda: (
        c.reconcile_turn(lambda: "reconciled", timeout=2), recon_done.set()))
    t_recon.start()
    # let the reconcile register as waiting
    for _ in range(50):
        if c.reconcile_waiting > 0:
            break
        time.sleep(0.01)
    assert c.reconcile_waiting == 1

    # a scheduled turn now must yield to the waiting reconcile
    assert c.try_scheduled_turn(lambda: "nope") == ("skipped", "reconcile_waiting")

    release.set()
    t_hold.join(2)
    assert recon_done.wait(2)


def test_scheduled_yields_while_reconcile_running(critic5=True):
    # critic #5: a scheduled turn arriving WHILE a reconcile is executing must
    # still skip with reason 'reconcile_waiting' (priority held through run_fn).
    c = TurnCoordinator()
    in_recon = threading.Event()
    release = threading.Event()

    def recon():
        c.reconcile_turn(lambda: (in_recon.set(), release.wait(2)))

    t = threading.Thread(target=recon)
    t.start()
    assert in_recon.wait(2)  # reconcile is now executing run_fn
    assert c.reconcile_waiting == 1  # indicator held through execution
    assert c.try_scheduled_turn(lambda: "nope") == ("skipped", "reconcile_waiting")
    release.set()
    t.join(2)
    assert c.reconcile_waiting == 0


def test_reconcile_best_effort_on_failure():
    c = TurnCoordinator()
    status, payload = c.reconcile_turn(lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert status == "error"  # caught, not raised
    # the lock is released after a failure -> a later turn still runs
    assert c.try_scheduled_turn(lambda: "ok") == ("ran", "ok")


def test_reconcile_worker_debounces_same_kind():
    c = TurnCoordinator()
    w = ReconcileWorker(c, debounce=0.05)
    fires = []
    for _ in range(5):
        w.trigger(lambda: fires.append(1), kind="human")
        time.sleep(0.005)  # all within the debounce window
    time.sleep(0.2)
    assert sum(fires) == 1  # coalesced to a single reconcile
    w.stop()


def test_reconcile_worker_distinct_kinds_each_fire():
    c = TurnCoordinator()
    w = ReconcileWorker(c, debounce=0.05)
    kinds = []
    w.trigger(lambda: kinds.append("a"), kind="human")
    w.trigger(lambda: kinds.append("b"), kind="market")
    time.sleep(0.2)
    assert set(kinds) == {"a", "b"}  # per-kind run_fn (C-4)
    w.stop()

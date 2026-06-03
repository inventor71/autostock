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


# ---- F38: start_priority_async (manual /research — top priority, queued) ---- #


def test_priority_async_runs_in_background_when_free():
    c = TurnCoordinator()
    ran = threading.Event()
    assert c.start_priority_async(lambda: ran.set(), kind="manual_research") == "started"
    assert ran.wait(2)  # run_fn executed on the background thread
    # the lock is released after the run -> a later turn still acquires
    assert c.try_scheduled_turn(lambda: "ok") == ("ran", "ok")


def test_priority_async_queues_behind_in_flight_turn_then_runs():
    # NOT dropped when a turn is in-flight: it reports "queued" and runs as soon as
    # the in-flight turn finishes (the deliberate human command must run).
    c = TurnCoordinator()
    held = threading.Event()
    release = threading.Event()
    t = threading.Thread(target=lambda: c.try_scheduled_turn(
        lambda: (held.set(), release.wait(2))))
    t.start()
    assert held.wait(2)
    ran = threading.Event()
    assert c.start_priority_async(lambda: ran.set(), kind="manual_research") == "queued"
    assert not ran.is_set()          # has not run yet — the other turn holds the lock
    release.set()                    # let the in-flight turn finish
    assert ran.wait(2)               # now the queued manual turn runs
    t.join(2)


def test_scheduled_turn_yields_to_queued_manual():
    # a scheduled turn must skip while a manual turn is queued (top priority).
    c = TurnCoordinator()
    held = threading.Event()
    release = threading.Event()
    t = threading.Thread(target=lambda: c.try_scheduled_turn(
        lambda: (held.set(), release.wait(2))))
    t.start()
    assert held.wait(2)
    assert c.start_priority_async(lambda: None, kind="manual_research") == "queued"
    assert c.manual_waiting == 1
    # a scheduled turn arriving now yields to the queued manual
    assert c.try_scheduled_turn(lambda: "nope") == ("skipped", "manual_waiting")
    release.set()
    t.join(2)


def test_reconcile_yields_to_queued_manual_then_both_run():
    # F38: a manual /research outranks reconcile/wake. While a manual is queued
    # behind an in-flight turn, a reconcile waits; the manual runs first, then the
    # reconcile (no drop).
    c = TurnCoordinator()
    held = threading.Event()
    release = threading.Event()
    order = []
    # occupy the lock with a scheduled turn
    t_hold = threading.Thread(target=lambda: c.try_scheduled_turn(
        lambda: (held.set(), release.wait(2))))
    t_hold.start()
    assert held.wait(2)
    # queue a manual turn (top priority) and a reconcile behind the held lock
    man_ran = threading.Event()
    assert c.start_priority_async(
        lambda: (order.append("manual"), man_ran.set()), kind="manual_research") == "queued"
    rec_ran = threading.Event()
    t_rec = threading.Thread(target=lambda: c.reconcile_turn(
        lambda: (order.append("reconcile"), rec_ran.set()), timeout=3))
    t_rec.start()
    time.sleep(0.1)  # let the reconcile reach its manual-yield wait
    release.set()    # free the lock
    assert man_ran.wait(2) and rec_ran.wait(2)
    assert order == ["manual", "reconcile"]  # manual ran before reconcile
    t_hold.join(2); t_rec.join(2)


def test_priority_async_is_non_blocking():
    # the CALLER must return immediately even if the turn itself is slow (FR-4):
    # the manual trigger arrives on the single CommandBus worker.
    c = TurnCoordinator()
    release = threading.Event()
    started = time.monotonic()
    assert c.start_priority_async(lambda: release.wait(2), kind="slow") == "started"
    assert time.monotonic() - started < 0.5  # did not wait for the 2s run_fn
    release.set()


def test_priority_async_releases_lock_on_failure():
    c = TurnCoordinator()
    done = threading.Event()

    def boom():
        try:
            raise RuntimeError("x")
        finally:
            done.set()

    assert c.start_priority_async(boom, kind="manual_research") == "started"
    assert done.wait(2)
    time.sleep(0.05)  # let the finally-release run after the exception
    assert c.try_scheduled_turn(lambda: "ok") == ("ran", "ok")  # lock freed
    assert c.manual_waiting == 0  # waiter counter cleaned up


def test_priority_async_on_done_reports_success():
    c = TurnCoordinator()
    done = threading.Event()
    got = {}

    def on_done(result, error):
        got["result"], got["error"] = result, error
        done.set()

    assert c.start_priority_async(lambda: "RES", kind="manual_research", on_done=on_done) == "started"
    assert done.wait(2)
    assert got == {"result": "RES", "error": None}
    assert c.try_scheduled_turn(lambda: "ok") == ("ran", "ok")


def test_priority_async_on_done_reports_failure():
    c = TurnCoordinator()
    done = threading.Event()
    got = {}

    def boom():
        raise RuntimeError("turn blew up")

    def on_done(result, error):
        got["result"], got["error"] = result, error
        done.set()

    assert c.start_priority_async(boom, kind="manual_research", on_done=on_done) == "started"
    assert done.wait(2)
    assert got["result"] is None and isinstance(got["error"], RuntimeError)
    assert "turn blew up" in str(got["error"])
    assert c.try_scheduled_turn(lambda: "ok") == ("ran", "ok")  # lock freed even on failure


def test_priority_async_on_done_runs_before_lock_release():
    # on_done must fire while the turn lock is still held, so post-turn state is
    # stable (no next turn can interleave). Assert the lock is busy during on_done.
    c = TurnCoordinator()
    done = threading.Event()
    locked_during = {}

    def on_done(result, error):
        locked_during["busy"] = not c._turn_lock.acquire(blocking=False)
        done.set()

    assert c.start_priority_async(lambda: "x", on_done=on_done) == "started"
    assert done.wait(2)
    assert locked_during["busy"] is True


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

"""TurnCoordinator + ReconcileWorker: serialize all LLM-session turns (NFR-1).

``claude --resume`` on one daily session id must never run twice concurrently, so
every turn (scheduled research/intraday/eod AND out-of-band reconcile) goes through
a single ``turn_lock``. Two distinct behaviors (C-1):

- ``try_scheduled_turn`` -- non-blocking: if a turn is in-flight, or a reconcile is
  waiting (priority, CQ-R1), the scheduled turn is **skipped, not queued**.
- ``reconcile_turn`` -- bounded-blocking with priority: it registers as waiting
  (so scheduled turns yield), then acquires; best-effort (failure logged, never
  raised, never kills the daemon -- BR-6.3).

ReconcileWorker debounces rapid triggers and keeps a run_fn **per trigger kind**
(C-4) so a future market-event wake (F3) can carry a different prompt than a human
reconcile, instead of one fixed run_fn.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from loguru import logger


class TurnCoordinator:
    def __init__(self) -> None:
        self._turn_lock = threading.Lock()
        self._waiters_lock = threading.Lock()
        self._reconcile_waiting = 0

    @property
    def reconcile_waiting(self) -> int:
        with self._waiters_lock:
            return self._reconcile_waiting

    def try_scheduled_turn(self, run_fn: Callable[[], Any]) -> tuple[str, Any]:
        """Run a scheduled turn IFF no turn is in-flight and no reconcile is
        waiting; otherwise skip (never queue). Returns ('ran', value) or
        ('skipped', reason)."""
        with self._waiters_lock:
            if self._reconcile_waiting > 0:
                logger.info("scheduled turn skipped: reconcile has priority")
                return ("skipped", "reconcile_waiting")
        if not self._turn_lock.acquire(blocking=False):
            logger.info("scheduled turn skipped: another turn in-flight")
            return ("skipped", "busy")
        try:
            return ("ran", run_fn())
        finally:
            self._turn_lock.release()

    def reconcile_turn(self, run_fn: Callable[[], Any], *, timeout: float = 600.0
                       ) -> tuple[str, Any]:
        """Acquire the turn lock with priority over scheduled turns, then run
        ``run_fn`` best-effort. Returns ('ran', value) / ('timeout', None) /
        ('error', exc).

        The waiting indicator is held for the WHOLE call (waiting + executing),
        not just the acquire, so a scheduled turn that arrives while a reconcile
        is *running* still yields with reason 'reconcile_waiting' rather than the
        weaker 'busy' -- preserving reconcile priority for a second reconcile
        queued behind it (critic #5)."""
        with self._waiters_lock:
            self._reconcile_waiting += 1
        try:
            if not self._turn_lock.acquire(timeout=timeout):
                logger.warning("reconcile turn timed out acquiring turn_lock ({}s)", timeout)
                return ("timeout", None)
            try:
                return ("ran", run_fn())
            except Exception as e:  # best-effort: never kill the daemon (BR-6.3)
                logger.error("reconcile turn failed (best-effort): {}", e)
                return ("error", e)
            finally:
                self._turn_lock.release()
        finally:
            with self._waiters_lock:
                self._reconcile_waiting -= 1


class ReconcileWorker:
    """Debounced, per-kind reconcile trigger with **independent per-kind timers**.

    Each kind (e.g. ``reconcile`` for human steering, ``wake`` for F3 market
    events) owns its own debounce timer, so a stream of ``wake`` triggers can no
    longer cancel/reset the ``human`` timer and starve it indefinitely
    (critic#2). Within a kind, rapid triggers coalesce (latest run_fn wins) and
    fire once. A per-kind ``timeout`` bounds the lock *acquisition* (wake gets a
    shorter one than human) — note this bounds *waiting*, not the LLM run itself,
    which is bounded by a turn-level timeout passed into the run_fn elsewhere.

    The shared ``turn_lock`` still serializes execution (NFR-1), so a human
    reconcile arriving while a wake turn is in-flight waits for that one turn to
    finish — an inherent, bounded cost of the single-session model, not removed
    here (CQ-R1)."""

    def __init__(self, coordinator: TurnCoordinator, debounce: float = 1.0,
                 *, default_timeout: float = 600.0) -> None:
        self._coord = coordinator
        self._debounce = debounce
        self._default_timeout = default_timeout
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[Callable[[], Any], float]] = {}
        self._timers: dict[str, threading.Timer] = {}
        self._stopped = False

    def trigger(self, run_fn: Callable[[], Any], *, kind: str = "reconcile",
                timeout: float | None = None) -> None:
        with self._lock:
            if self._stopped:
                return
            self._pending[kind] = (run_fn, self._default_timeout if timeout is None else timeout)
            existing = self._timers.get(kind)
            if existing is not None:
                existing.cancel()  # reset THIS kind's debounce only
            timer = threading.Timer(self._debounce, self._fire, args=(kind,))
            timer.daemon = True
            self._timers[kind] = timer
            timer.start()

    def _fire(self, kind: str) -> None:
        with self._lock:
            entry = self._pending.pop(kind, None)
            self._timers.pop(kind, None)
        if entry is None:
            return
        run_fn, timeout = entry
        try:
            self._coord.reconcile_turn(run_fn, timeout=timeout)
        except Exception as e:  # belt-and-suspenders; reconcile_turn is already best-effort
            logger.error("reconcile worker fire failed ({}): {}", kind, e)

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()

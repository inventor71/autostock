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
        ('error', exc)."""
        with self._waiters_lock:
            self._reconcile_waiting += 1
        acquired = False
        try:
            acquired = self._turn_lock.acquire(timeout=timeout)
        finally:
            with self._waiters_lock:
                self._reconcile_waiting -= 1
        if not acquired:
            logger.warning("reconcile turn timed out acquiring turn_lock ({}s)", timeout)
            return ("timeout", None)
        try:
            return ("ran", run_fn())
        except Exception as e:  # best-effort: never kill the daemon (BR-6.3)
            logger.error("reconcile turn failed (best-effort): {}", e)
            return ("error", e)
        finally:
            self._turn_lock.release()


class ReconcileWorker:
    """Debounced, per-kind reconcile trigger. Rapid triggers of the same kind
    coalesce into one turn; distinct kinds each fire once (latest run_fn wins)."""

    def __init__(self, coordinator: TurnCoordinator, debounce: float = 1.0) -> None:
        self._coord = coordinator
        self._debounce = debounce
        self._lock = threading.Lock()
        self._pending: dict[str, Callable[[], Any]] = {}
        self._timer: threading.Timer | None = None
        self._stopped = False

    def trigger(self, run_fn: Callable[[], Any], *, kind: str = "reconcile") -> None:
        with self._lock:
            if self._stopped:
                return
            self._pending[kind] = run_fn  # coalesce within kind
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        with self._lock:
            pending = dict(self._pending)
            self._pending.clear()
            self._timer = None
        for kind, run_fn in pending.items():
            try:
                self._coord.reconcile_turn(run_fn)
            except Exception as e:  # belt-and-suspenders; reconcile_turn is already best-effort
                logger.error("reconcile worker fire failed ({}): {}", kind, e)

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

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
import time
from typing import Any, Callable

from loguru import logger


class TurnCoordinator:
    """Serializes all LLM-session turns with three priority tiers (highest first):

    1. **manual** (``start_priority_async``) — a human's explicit ``/research`` (F38).
       Top priority and **never dropped**: it blocks (bounded) for the lock on a
       background thread and runs as soon as the current turn frees. Scheduled AND
       reconcile/wake turns yield to a queued manual turn (a deliberate human command
       must not be bumped by an automatic turn).
    2. **reconcile / wake** (``reconcile_turn``) — out-of-band human-reconcile and
       event-driven wake turns. Priority over scheduled; yields to a queued manual.
    3. **scheduled** (``try_scheduled_turn``) — morning/intraday/eod; skip-if-busy.
    """

    def __init__(self) -> None:
        self._turn_lock = threading.Lock()
        self._waiters_lock = threading.Lock()
        self._reconcile_waiting = 0
        self._manual_waiting = 0  # F38: a manual /research is queued (top priority)

    @property
    def reconcile_waiting(self) -> int:
        with self._waiters_lock:
            return self._reconcile_waiting

    @property
    def manual_waiting(self) -> int:
        with self._waiters_lock:
            return self._manual_waiting

    def try_scheduled_turn(self, run_fn: Callable[[], Any]) -> tuple[str, Any]:
        """Run a scheduled turn IFF no turn is in-flight and nothing higher-priority
        is waiting (manual or reconcile); otherwise skip (never queue). Returns
        ('ran', value) or ('skipped', reason)."""
        with self._waiters_lock:
            if self._manual_waiting > 0:
                logger.info("scheduled turn skipped: manual turn has priority")
                return ("skipped", "manual_waiting")
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

    def start_priority_async(self, run_fn: Callable[[], Any], *, kind: str = "manual",
                             on_done: Callable[[Any, BaseException | None], None] | None = None,
                             timeout: float = 1800.0) -> str:
        """Start a **top-priority, never-dropped** turn on a background thread,
        returning immediately. The human's explicit ``/research`` (F38) must run, not
        be silently bumped by an automatic scheduled/wake/reconcile turn — so unlike
        ``try_scheduled_turn`` this does NOT skip on contention: it registers as a
        manual waiter (scheduled + reconcile turns then yield to it) and **blocks for
        the lock** on a daemon thread, running as soon as the current turn (if any)
        finishes. The caller (the single CommandBus worker) is never blocked — the
        wait happens on the spawned thread. The shared ``turn_lock`` still serializes
        sessions (NFR-1: never two concurrent ``claude --resume`` turns).

        ``on_done(result, error)`` -- if given -- is called when the turn finishes
        (``error`` is the exception, or ``None`` on success, or a ``TimeoutError`` if
        the lock could not be acquired within ``timeout``), still **holding the turn
        lock** so post-turn state (e.g. the orchestrator's last_new_decisions) is
        stable when the completion is reported. It must not block (F38 wires it to a
        non-blocking ``bus.submit`` of the completion event); its exceptions are
        swallowed.

        Returns ``"started"`` (the lock was free — runs now) or ``"queued"`` (a turn
        is in-flight — runs next). Never ``"busy"``/``"skipped"``; the turn is not
        dropped. Completion is observed via turns.jsonl + the ``on_done`` event."""
        with self._waiters_lock:
            self._manual_waiting += 1
        free = not self._turn_lock.locked()  # best-effort hint for the ack only

        def _run() -> None:
            result: Any = None
            error: BaseException | None = None
            try:
                if not self._turn_lock.acquire(timeout=timeout):
                    error = TimeoutError(f"turn lock busy > {timeout:g}s")
                    logger.warning("manual turn ({}) timed out acquiring turn_lock ({}s)",
                                   kind, timeout)
                    if on_done is not None:
                        try:
                            on_done(None, error)
                        except Exception as e:
                            logger.error("manual turn ({}) on_done failed: {}", kind, e)
                    return
                try:
                    try:
                        result = run_fn()
                    except Exception as e:  # best-effort: never kill the daemon (BR-6.3)
                        error = e
                        logger.error("manual turn ({}) failed (best-effort): {}", kind, e)
                    finally:
                        try:
                            if on_done is not None:
                                on_done(result, error)  # under the lock: state stable
                        except Exception as e:
                            logger.error("manual turn ({}) on_done failed: {}", kind, e)
                finally:
                    self._turn_lock.release()
            finally:
                with self._waiters_lock:
                    self._manual_waiting -= 1

        threading.Thread(target=_run, name=f"manual-turn-{kind}", daemon=True).start()
        logger.info("manual turn ({}) {} (top priority)", kind,
                    "started" if free else "queued behind the in-flight turn")
        return "started" if free else "queued"

    def reconcile_turn(self, run_fn: Callable[[], Any], *, timeout: float = 600.0
                       ) -> tuple[str, Any]:
        """Acquire the turn lock with priority over scheduled turns, then run
        ``run_fn`` best-effort. Returns ('ran', value) / ('timeout', None) /
        ('error', exc).

        The waiting indicator is held for the WHOLE call (waiting + executing),
        not just the acquire, so a scheduled turn that arrives while a reconcile
        is *running* still yields with reason 'reconcile_waiting' rather than the
        weaker 'busy' -- preserving reconcile priority for a second reconcile
        queued behind it (critic #5).

        F38: a queued **manual** turn (``/research``) outranks reconcile/wake, so
        this first waits (bounded by ``timeout``) for any queued manual turn to take
        the lock before contending for it. The reconcile is not dropped — it runs
        right after the manual turn."""
        deadline = time.monotonic() + timeout
        with self._waiters_lock:
            self._reconcile_waiting += 1
        try:
            # F38: let a queued manual /research go first (top priority), bounded so
            # a stuck manual turn can't starve reconcile past its timeout.
            while self.manual_waiting > 0 and time.monotonic() < deadline:
                time.sleep(0.05)
            remaining = max(0.0, deadline - time.monotonic())
            if not self._turn_lock.acquire(timeout=remaining):
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

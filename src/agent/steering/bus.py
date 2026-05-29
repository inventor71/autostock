"""CommandBus: the single thread that owns all broker mutation + executor cursor.

Every side-effecting steering action -- a confirmed file-drop command, an approved
pending decision, the scheduler's executor phase (funnelled here, NOT called on the
scheduler thread) -- runs as a work item on ONE worker thread. This makes broker
order races and cursor read-modify-write races structurally impossible *inside the
daemon* (BR-7.1'). Read-only calls and the agent subprocess's own broker are out of
scope of this lock (BR-7.2').

Two priority lanes: emergency items (kill/flatten/pause/halt) jump ahead of queued
normal work. A long normal item (a multi-symbol executor batch) can cooperatively
yield by polling ``emergency_pending()`` -- an in-flight broker HTTP call itself is
not preemptible (~11s worst case, BR-13).
"""

from __future__ import annotations

import itertools
import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from loguru import logger

EMERGENCY = 0
NORMAL = 1


class WorkResult:
    """A tiny future: the worker fills it; the submitter may wait on it."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self.value: Any = None
        self.error: BaseException | None = None

    def _set(self, value: Any = None, error: BaseException | None = None) -> None:
        self.value, self.error = value, error
        self._event.set()

    def done(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float | None = None) -> Any:
        if not self._event.wait(timeout):
            raise TimeoutError("command did not complete in time")
        if self.error is not None:
            raise self.error
        return self.value


@dataclass(order=True)
class _Item:
    priority: int
    seq: int
    fn: Callable[[], Any] = field(compare=False)
    result: WorkResult = field(compare=False)


class CommandBus:
    def __init__(self) -> None:
        self._q: "queue.PriorityQueue[_Item]" = queue.PriorityQueue()
        self._seq = itertools.count()
        self._emergency_waiting = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- lifecycle -------------------------------------------------------- #
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="CommandWorker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self.submit(lambda: None)  # wake the worker out of its blocking get()
        if self._thread is not None:
            self._thread.join(timeout)

    # ---- submission ------------------------------------------------------- #
    def submit(self, fn: Callable[[], Any], *, emergency: bool = False) -> WorkResult:
        """Enqueue ``fn`` to run on the worker; returns a WorkResult to wait on."""
        res = WorkResult()
        if emergency:
            with self._lock:
                self._emergency_waiting += 1
        self._q.put(_Item(EMERGENCY if emergency else NORMAL, next(self._seq), fn, res))
        return res

    def submit_and_wait(self, fn: Callable[[], Any], *, emergency: bool = False,
                        timeout: float | None = None) -> Any:
        return self.submit(fn, emergency=emergency).wait(timeout)

    def emergency_pending(self) -> bool:
        """True if an emergency item is queued -- lets a long normal item yield."""
        with self._lock:
            return self._emergency_waiting > 0

    # ---- worker loop ------------------------------------------------------ #
    def _run(self) -> None:
        while True:
            try:
                item = self._q.get(timeout=0.5)
            except queue.Empty:
                if self._stop.is_set():
                    return
                continue
            if item.priority == EMERGENCY:
                with self._lock:
                    self._emergency_waiting -= 1
            try:
                item.result._set(value=item.fn())
            except Exception as e:  # one bad item must not kill the worker (BR-8.2)
                logger.error("CommandWorker item failed: {}", e)
                item.result._set(error=e)
            finally:
                self._q.task_done()
            if self._stop.is_set() and self._q.empty():
                return

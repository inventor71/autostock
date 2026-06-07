"""SteeringState (E3/E4/E5/E6): the daemon's in-memory + persisted control state.

Holds RunState (pause/halt), the per-symbol HumanLock state machine, the
PendingApproval queue, and standing Directives. All mutation goes through a
single ``state_lock`` (BR-7/P1.4). These files are written ONLY by the daemon
(unlike the cross-process command/question channels), so an atomic full rewrite
(temp + os.replace) is race-free here.

ET-date scoping (P1.5): every scoped entry carries the ET date it belongs to.
On access, entries from a past ET date are treated as cleared (lazy expiry); a
daily sweep persists the cleanup so a multi-day daemon never restarts to do it.
A same-day restart restores state from the persisted files (BR-3.3/4.8).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from src.core.markettime import et_today
from src.agent.steering.jsonl import atomic_write_text
from src.agent.steering.records import (
    Directive,
    LockState,
    PendingApproval,
    RunState,
)


def _decision_fingerprint(d) -> tuple:
    """Idempotency key for parking (BR-4.2 / P2): symbol+action+levels."""
    return (
        getattr(d, "symbol", None),
        getattr(d, "action", None),
        getattr(d, "limit", None),
        getattr(d, "stop", None),
        getattr(d, "target", None),
    )


class SteeringState:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._lock = threading.RLock()
        self._run = RunState()
        self._locks: dict[str, LockState] = {}
        self._pending: dict[int, PendingApproval] = {}
        self._directives: dict[str, Directive] = {}
        self._pending_counter = 0
        self._load()

    # ---- persistence paths ------------------------------------------------ #
    @property
    def _run_file(self) -> Path:
        return self.root / "run_state.json"

    @property
    def _locks_file(self) -> Path:
        return self.root / "human_locks.json"

    @property
    def _pending_file(self) -> Path:
        return self.root / "pending_approvals.json"

    @property
    def _directives_file(self) -> Path:
        return self.root / "directives.json"

    # ---- load / persist --------------------------------------------------- #
    def _load(self) -> None:
        today = et_today().isoformat()
        if self._run_file.exists():
            try:
                rs = RunState.model_validate_json(self._run_file.read_text())
                # BR-3.3: restore only within the same trading day
                self._run = rs if rs.et_date == today else RunState(et_date=today)
            except Exception:
                self._run = RunState(et_date=today)
        if self._locks_file.exists():
            try:
                raw = json.loads(self._locks_file.read_text())
                self._locks = {
                    s: LockState.model_validate(v)
                    for s, v in raw.items()
                    if LockState.model_validate(v).et_date == today
                }
            except Exception:
                self._locks = {}
        if self._pending_file.exists():
            try:
                raw = json.loads(self._pending_file.read_text())
                items = [PendingApproval.model_validate(v) for v in raw]
                self._pending = {p.id: p for p in items if p.et_date == today}
                # rehydrate counter = max+1 so ids never collide after restart (critic #3)
                self._pending_counter = max((p.id for p in items), default=0)
            except Exception:
                self._pending = {}
        if self._directives_file.exists():
            try:
                raw = json.loads(self._directives_file.read_text())
                self._directives = {d.id: d for d in (Directive.model_validate(v) for v in raw)}
            except Exception:
                self._directives = {}

    def _persist_run(self) -> None:
        atomic_write_text(self._run_file, self._run.model_dump_json())

    def _persist_locks(self) -> None:
        atomic_write_text(
            self._locks_file,
            json.dumps({s: l.model_dump(mode="json") for s, l in self._locks.items()}),
        )

    def _persist_pending(self) -> None:
        atomic_write_text(
            self._pending_file,
            json.dumps([p.model_dump(mode="json") for p in self._pending.values()]),
        )

    def _persist_directives(self) -> None:
        atomic_write_text(
            self._directives_file,
            json.dumps([d.model_dump(mode="json") for d in self._directives.values()]),
        )

    # ---- RunState (BR-3) -------------------------------------------------- #
    def run_state(self) -> RunState:
        with self._lock:
            return self._run.model_copy()

    def set_paused(self, value: bool) -> None:
        with self._lock:
            self._run.paused = value
            self._run.et_date = et_today().isoformat()
            self._persist_run()

    def set_entries_halted(self, value: bool) -> None:
        with self._lock:
            self._run.entries_halted = value
            self._run.et_date = et_today().isoformat()
            self._persist_run()

    # ---- HumanLock state machine (BR-4) ----------------------------------- #
    def _live_lock(self, symbol: str) -> LockState | None:
        """Lazy expiry: a lock from a past ET date is treated as gone."""
        lock = self._locks.get(symbol)
        if lock is None:
            return None
        if lock.et_date != et_today().isoformat():
            del self._locks[symbol]
            return None
        return lock

    def lock_status(self, symbol: str) -> str | None:
        with self._lock:
            lock = self._live_lock(symbol.upper())
            return lock.status if lock else None

    def lock_symbol(self, symbol: str) -> None:
        """BR-4.1/4.11: a human trade locks the symbol (and resets denied->locked)."""
        symbol = symbol.upper()
        with self._lock:
            self._locks[symbol] = LockState(
                status="locked", reject_count=0, et_date=et_today().isoformat()
            )
            self._persist_locks()

    def unlock_symbol(self, symbol: str) -> list[int]:
        """BR-4.7/4.10: clear the lock and resolve any outstanding pendings for it.
        Returns the ids of pendings that were resolved (rejected) by the unlock."""
        symbol = symbol.upper()
        with self._lock:
            self._locks.pop(symbol, None)
            resolved = [
                p.id for p in self._pending.values()
                if p.status == "pending" and p.decision.symbol == symbol
            ]
            for pid in resolved:
                self._pending[pid].status = "rejected"
                self._pending[pid].reason = "unlocked"
            self._persist_locks()
            if resolved:
                self._persist_pending()
            return resolved

    # ---- PendingApproval queue (BR-4.2/4.4/4.5, BR-5) --------------------- #
    def add_pending(self, decision) -> PendingApproval | None:
        """Park an agent discretionary decision. Idempotent on the decision
        fingerprint (P2): a re-processed batch never double-parks the same one.
        Returns the PendingApproval, or None if an identical one is already pending."""
        with self._lock:
            fp = _decision_fingerprint(decision)
            for p in self._pending.values():
                if p.status == "pending" and _decision_fingerprint(p.decision) == fp:
                    return None  # already parked
            self._pending_counter += 1
            pa = PendingApproval(
                id=self._pending_counter,
                decision=decision.model_dump() if hasattr(decision, "model_dump") else decision,
                et_date=et_today().isoformat(),
            )
            self._pending[pa.id] = pa
            self._persist_pending()
            return pa

    def list_pending(self) -> list[PendingApproval]:
        with self._lock:
            today = et_today().isoformat()
            return [
                p for p in self._pending.values()
                if p.status == "pending" and p.et_date == today
            ]

    def approve(self, pid: int) -> PendingApproval | None:
        """BR-4.3: mark approved + unlock the symbol. Caller executes the decision."""
        with self._lock:
            pa = self._pending.get(pid)
            # date-scoped consistently with list_pending: a past-day pending is
            # treated as gone (critic #3) so the queue/lock map never disagree.
            if pa is None or pa.status != "pending" or pa.et_date != et_today().isoformat():
                return None
            pa.status = "approved"
            self._locks.pop(pa.decision.symbol.upper(), None)  # unlock on approve
            self._persist_pending()
            self._persist_locks()
            return pa

    def reject(self, pid: int, reason: str = "") -> tuple[PendingApproval | None, str | None]:
        """BR-4.4: mark rejected, bump the symbol's reject_count (2 -> denied).
        Returns (pending, new_status) where new_status is 'locked'|'denied'|None."""
        with self._lock:
            pa = self._pending.get(pid)
            if pa is None or pa.status != "pending" or pa.et_date != et_today().isoformat():
                return None, None
            pa.status = "rejected"
            pa.reason = reason
            sym = pa.decision.symbol.upper()
            lock = self._live_lock(sym) or LockState(et_date=et_today().isoformat())
            lock.reject_count = min(lock.reject_count + 1, 2)
            lock.status = "denied" if lock.reject_count >= 2 else "locked"
            self._locks[sym] = lock
            self._persist_pending()
            self._persist_locks()
            return pa, lock.status

    # ---- Directives (BR-6 trigger source / E6) ---------------------------- #
    def add_directive(self, text: str) -> Directive:
        with self._lock:
            d = Directive(text=text)
            self._directives[d.id] = d
            self._persist_directives()
            return d

    def active_directives(self) -> list[Directive]:
        with self._lock:
            return [d for d in self._directives.values() if d.active]

    def clear_directive(self, which: str) -> int:
        """``which`` = an id or 'all'. Returns count cleared."""
        with self._lock:
            n = 0
            for d in self._directives.values():
                if d.active and (which == "all" or d.id == which):
                    d.active = False
                    n += 1
            if n:
                self._persist_directives()
            return n

    # ---- daily sweep (P1.5) ---------------------------------------------- #
    def sweep_expired(self) -> None:
        """Drop past-ET-date scoped state and persist the cleanup (midnight job)."""
        today = et_today().isoformat()
        with self._lock:
            self._locks = {s: l for s, l in self._locks.items() if l.et_date == today}
            self._pending = {i: p for i, p in self._pending.items() if p.et_date == today}
            if self._run.et_date != today:
                self._run = RunState(et_date=today)
            self._persist_locks()
            self._persist_pending()
            self._persist_run()

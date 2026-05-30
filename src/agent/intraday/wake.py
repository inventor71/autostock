"""WakeDetector — event-driven out-of-band wake turns (FR-4).

Runs on a short (5s) scheduler job. It only ever reads CACHED data (the in-proc
snapshot + ``BarCache``) — never a synchronous broker/market fetch on the
scheduler thread (critic#3) — turns detected events into a WakeDetector-owned
buffer, and triggers the shared ``ReconcileWorker`` with ``kind="wake"``. The
buffer is drained at FIRE time (not trigger time) so events accumulated across
debounce ticks coalesce into ONE wake turn (Q5=A / critic#2).

Gating (FR-7, Q7=A): ``paused`` suppresses all wakes (with a log); when
``entries_halted`` the detector drops only ``entry_inducing`` events — gate.py
does NOT enforce halts (critic#4), so suppression must happen here.
"""

from __future__ import annotations

import threading

from loguru import logger

from src.agent.intraday.abnormal import AbnormalConfig, detect_abnormal
from src.agent.intraday.records import WakeEvent

_EXIT_KW = ("stop", "tighten", "trim", "exit", "sell", "reduce", "protect")
_ENTRY_KW = ("buy", "add", "enter", "long", "scale", "accumulate")


def classify_watch_entry_inducing(trigger) -> bool:
    """Whether a met watch trigger could induce a new entry (pure, fail-closed).

    Exit/stop intents -> False (always allowed, even when halted). Entry intents
    -> True. Ambiguous upside breakouts default to True so the entries-halted
    guarantee holds (gate.py can't block the BUY, so the wake must not fire)."""
    intent = (trigger.intent or "").lower()
    if any(k in intent for k in _EXIT_KW):
        return False
    if any(k in intent for k in _ENTRY_KW):
        return True
    return trigger.condition in ("price_above", "close_above")


class WakeDetector:
    def __init__(self, *, snapshot_fn, state, watch_store, bar_cache, reconcile_worker,
                 wake_runner, config: AbnormalConfig | None = None,
                 wake_timeout: float = 120.0):
        self._snapshot_fn = snapshot_fn          # () -> last_snapshot dict | None
        self._state = state                       # SteeringState (run_state)
        self._watch = watch_store
        self._bars = bar_cache
        self._worker = reconcile_worker
        self._wake_runner = wake_runner           # (list[WakeEvent]) -> Any
        self._cfg = config or AbnormalConfig()
        self._wake_timeout = wake_timeout
        self._buffer: list[WakeEvent] = []
        self._lock = threading.Lock()
        self._abnormal_fired: set[str] = set()    # latch: one wake per abnormal episode

    # ---- scheduler entry point (5s) --------------------------------------- #
    def detect_wakes(self) -> None:
        try:
            rs = self._state.run_state()
            if getattr(rs, "paused", False):
                logger.info("wake suppressed: run paused")  # FR-7 (only trace while paused)
                return
            snap = self._snapshot_fn() or {}
            events = (self._fill_events(snap)
                      + self._abnormal_events(snap)
                      + self._watch_events(snap))
            if getattr(rs, "entries_halted", False):
                events = [e for e in events if not e.entry_inducing]  # Q7=A
            if not events:
                return
            with self._lock:
                self._buffer.extend(events)
            self._worker.trigger(self._fire_wake, kind="wake", timeout=self._wake_timeout)
        except Exception as e:  # best-effort: never kill the scheduler (NFR-4)
            logger.error("wake detection failed (continuing): {}", e)

    def _fire_wake(self):
        with self._lock:
            events = self._buffer
            self._buffer = []
        if not events:
            return None
        return self._wake_runner(events)

    # ---- detectors (all read cached data only) ---------------------------- #
    def _fill_events(self, snap) -> list[WakeEvent]:
        out = []
        for f in snap.get("fills", []) or []:
            sell = str(f.get("side")) == "sell"
            kind = "protective_reassess" if sell else "new_fill"
            out.append(WakeEvent(
                kind=kind, symbol=str(f.get("symbol", "")),
                reason=f"{f.get('side')} {f.get('qty')} {f.get('symbol')} @ {f.get('price')}",
                payload=dict(f), entry_inducing=False))
        return out

    def _symbols(self, snap) -> list[str]:
        held = list((snap.get("positions") or {}).keys())
        watched = []
        try:
            watched = [t.symbol for t in self._watch.active()] if self._watch else []
        except Exception:
            pass
        return list(dict.fromkeys(held + watched))

    def _abnormal_events(self, snap) -> list[WakeEvent]:
        out = []
        for sym in self._symbols(snap):
            price = self._bars.get_price(sym)
            bars = self._bars.get_bars(sym)
            ref = None
            if bars is not None and len(bars) > 0:
                try:
                    ref = float(bars["open"].iloc[0])
                except Exception:
                    ref = None
            sig = detect_abnormal(sym, price, ref, bars, self._cfg)
            if sig is None:
                self._abnormal_fired.discard(sym)  # episode cleared -> re-armable
                continue
            if sym in self._abnormal_fired:
                continue  # already woke for this ongoing episode
            self._abnormal_fired.add(sym)
            upward = sig.kind == "price" and price is not None and ref is not None and price > ref
            out.append(WakeEvent(kind="abnormal_move", symbol=sym, reason=sig.reason,
                                 payload=sig.model_dump(mode="json"), entry_inducing=upward))
        return out

    def _watch_events(self, snap) -> list[WakeEvent]:
        if not self._watch:
            return []
        out = []
        for t in self._watch.active():
            if self._watch.is_fired(t.id):
                continue
            if not self._watch_met(t):
                continue
            self._watch.mark_fired(t.id)
            out.append(WakeEvent(
                kind="watch_trigger", symbol=t.symbol,
                reason=f"{t.symbol} {t.condition} {t.level} met (intent: {t.intent or 'n/a'})",
                payload={"id": t.id, "condition": t.condition, "level": t.level,
                         "intent": t.intent},
                entry_inducing=classify_watch_entry_inducing(t)))
        return out

    def _watch_met(self, t) -> bool:
        if t.condition in ("price_above", "price_below"):
            price = self._bars.get_price(t.symbol)
            if price is None:
                return False
            return price > t.level if t.condition == "price_above" else price < t.level
        # close_above / close_below: use the last completed bar's close
        bars = self._bars.get_bars(t.symbol)
        if bars is None or len(bars) == 0:
            return False
        try:
            close = float(bars["close"].iloc[-1])
        except Exception:
            return False
        return close > t.level if t.condition == "close_above" else close < t.level

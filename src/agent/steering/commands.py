"""Command verb handlers: wire a validated SteeringCommand to state/executor/broker.

Runs ON the CommandBus worker thread (the sole broker-mutation thread). Trades go
through the SAME RiskManager->Broker gate as the agent (BR-2.1): SELL/flatten reuse
``executor.execute_decision`` (RiskManager sizes the exit), BUY uses an explicit-size
bracket helper (the human sets size; protection is still attached). Each handled
command emits an outcome event (corr_id), writes an InterventionRecord, and -- for
book-changing actions -- triggers an async reconcile so the agent stays consistent.
Off-hours trades are queued for the market-open drain (BR-2.7).
"""

from __future__ import annotations

import math
from typing import Callable

from loguru import logger

from src.agent.executor import DecisionExecutor
from src.agent.journal import Decision
from src.agent.steering.channel import SteeringChannel
from src.agent.steering.records import InterventionRecord, SteeringCommand
from src.agent.steering.state import SteeringState
from src.agent.steering.turns import ReconcileWorker
from src.core.models import Order
from src.core.types import OrderClass, OrderSide, OrderType

_KIND = {
    "buy": "trade", "sell": "trade", "flatten": "trade", "flatten_all": "trade", "stop": "lock",
    "pause": "lifecycle", "resume": "lifecycle", "halt_entries": "lifecycle",
    "allow_entries": "lifecycle", "kill": "lifecycle",
    "approve": "approval", "reject": "approval", "unlock": "lock", "cancel": "lifecycle",
    "note": "note", "directive": "directive", "directive_clear": "directive", "answer": "directive",
}


def build_human_buy(symbol: str, size: float, unit: str, price: float | None,
                    atr: float | None, risk_manager) -> Order | None:
    """Build a human BUY order at the human's explicit size ($ notional or shares),
    with a resting protective bracket (ATR-derived stop) when a stop can be resolved;
    otherwise a plain market buy (polled backup covers). Shares are floored to whole
    units -- Alpaca rejects fractional bracket legs (F2 finding)."""
    if price is None or price <= 0:
        return None
    if unit == "$":
        qty = math.floor(size / price)
    elif unit == "sh":
        qty = math.floor(size)
    else:
        return None
    if qty <= 0:
        return None
    stop = risk_manager._resolve_stop(price, None, atr)
    if stop is None:  # no ATR/level -> simple market buy; polled stop backup applies
        return Order(symbol=symbol, side=OrderSide.BUY, qty=float(qty))
    target = price + risk_manager.default_risk_reward * (price - stop)
    return Order(
        symbol=symbol, side=OrderSide.BUY, qty=float(qty),
        order_type=OrderType.MARKET, order_class=OrderClass.BRACKET,
        take_profit_price=round(target, 2), stop_loss_price=round(stop, 2),
        time_in_force="gtc",
    )


class CommandHandler:
    def __init__(self, channel: SteeringChannel, state: SteeringState,
                 executor: DecisionExecutor, *,
                 reconcile_worker: ReconcileWorker | None = None,
                 reconcile_run_fn: Callable[[], object] | None = None):
        self.channel = channel
        self.state = state
        self.executor = executor
        self.broker = executor.broker
        self.risk_manager = executor.risk_manager
        self.data_provider = executor.data_provider
        self.journal = executor.journal
        self.reconcile_worker = reconcile_worker
        self.reconcile_run_fn = reconcile_run_fn
        self._log_file = self.journal.root / "human_directives.jsonl"

    # ---- dispatch --------------------------------------------------------- #
    def handle(self, cmd: SteeringCommand) -> None:
        handler = getattr(self, f"_v_{cmd.verb}", None)
        try:
            if handler is None:
                self._emit(cmd, "error", f"unknown verb {cmd.verb}")
            else:
                handler(cmd)
        except Exception as e:  # never kill the worker (BR-8.2)
            logger.exception("steering command {} failed", cmd.verb)
            self._emit(cmd, "error", str(e))
        finally:
            self.channel.mark_processed(cmd.id)

    # ---- helpers ---------------------------------------------------------- #
    def _emit(self, cmd: SteeringCommand, outcome: str, detail: str = "") -> None:
        self.channel.emit_outcome(cmd.id, outcome, detail)
        rec = InterventionRecord(
            kind=_KIND.get(cmd.verb, "note"),
            raw=str(cmd.args.get("raw", cmd.verb)),
            command=cmd.verb,
            args={k: v for k, v in cmd.args.items() if k != "raw"},
            outcome=outcome, detail=detail,
            rationale=str(cmd.args.get("reason", "")),
        )
        self.journal.root.mkdir(parents=True, exist_ok=True)
        with self._log_file.open("a", encoding="utf-8") as fh:
            fh.write(rec.model_dump_json() + "\n")

    def _reconcile(self) -> None:
        if self.reconcile_worker is not None and self.reconcile_run_fn is not None:
            self.reconcile_worker.trigger(self.reconcile_run_fn, kind="human")

    def _market_open(self) -> bool:
        try:
            return self.broker.is_market_open()
        except Exception:
            return False

    def _flatten_symbol(self, sym: str) -> None:
        opens = self.broker.get_open_orders(sym)
        if opens:
            self.executor._cancel_and_wait(sym, opens)  # release qty before close
        self.broker.close_position(sym)

    def _flatten_all_now(self) -> int:
        syms = [p.symbol.upper() for p in self.broker.get_all_positions()]
        for s in syms:
            self._flatten_symbol(s)
            self.state.lock_symbol(s)
        return len(syms)

    def _sell_fraction(self, size: float, unit: str, qty: float, sym: str) -> float:
        if unit == "%":
            return max(0.0, min(1.0, size / 100.0))
        if unit == "sh":
            return max(0.0, min(1.0, size / qty)) if qty > 0 else 0.0
        if unit == "$":
            price = self.data_provider.get_latest_price(sym)
            if not price or price <= 0 or qty <= 0:
                return 0.0
            return max(0.0, min(1.0, (size / price) / qty))
        return 0.0

    # ---- trade verbs ------------------------------------------------------ #
    def _v_buy(self, cmd: SteeringCommand) -> None:
        sym = str(cmd.args["symbol"]).upper()
        if not self._market_open():
            self.channel.queue_offhours(cmd)
            self._emit(cmd, "deferred", "market closed; queued for next open")
            return
        price = self.data_provider.get_latest_price(sym)
        atr = self.executor._atr(sym)
        order = build_human_buy(sym, float(cmd.args["size"]), str(cmd.args["unit"]),
                                price, atr, self.risk_manager)
        if order is None:
            self._emit(cmd, "no_order", "size rounds to 0 shares or no price")
            return
        filled = self.broker.submit_order(order)
        self.state.lock_symbol(sym)
        bracket = " (bracket)" if order.order_class == OrderClass.BRACKET else ""
        self._emit(cmd, "executed", f"BUY {order.qty} {sym}{bracket}")
        self._reconcile()

    def _v_sell(self, cmd: SteeringCommand) -> None:
        sym = str(cmd.args["symbol"]).upper()
        if not self._market_open():
            self.channel.queue_offhours(cmd)
            self._emit(cmd, "deferred", "market closed; queued for next open")
            return
        pos = self.broker.get_position(sym)
        if pos is None or pos.qty <= 0:
            self._emit(cmd, "no_order", f"no position in {sym}")
            return
        frac = self._sell_fraction(float(cmd.args["size"]), str(cmd.args["unit"]), pos.qty, sym)
        if frac <= 0:
            self._emit(cmd, "no_order", "sell size rounds to 0")
            return
        outcome = self.executor.execute_decision(
            Decision(symbol=sym, action="SELL", source="human", sell_pct=frac))
        self.state.lock_symbol(sym)
        self._emit(cmd, outcome.status, outcome.detail or f"SELL {frac:.0%} {sym}")
        self._reconcile()

    def _v_flatten(self, cmd: SteeringCommand) -> None:
        sym = str(cmd.args["symbol"]).upper()
        if not self._market_open():
            self.channel.queue_offhours(cmd)
            self._emit(cmd, "deferred", "market closed; queued for next open")
            return
        if self.broker.get_position(sym) is None:
            self._emit(cmd, "no_order", f"no position in {sym}")
            return
        self._flatten_symbol(sym)
        self.state.lock_symbol(sym)
        self._emit(cmd, "executed", f"flattened {sym}")
        self._reconcile()

    def _v_flatten_all(self, cmd: SteeringCommand) -> None:
        if not self._market_open():
            self.channel.queue_offhours(cmd)
            self._emit(cmd, "deferred", "market closed; queued for next open")
            return
        n = self._flatten_all_now()
        self._emit(cmd, "executed", f"flattened {n} positions")
        self._reconcile()

    def _v_stop(self, cmd: SteeringCommand) -> None:
        # protective management -> NOT a lock trigger (BLM 1.1)
        sym = str(cmd.args["symbol"]).upper()
        if not self._market_open():
            self.channel.queue_offhours(cmd)
            self._emit(cmd, "deferred", "market closed; queued for next open")
            return
        outcome = self.executor.execute_decision(
            Decision(symbol=sym, action="ADJUST_STOP", source="human", stop=float(cmd.args["price"])))
        self._emit(cmd, outcome.status, outcome.detail or f"stop {sym} -> {cmd.args['price']}")
        self._reconcile()

    # ---- lifecycle verbs -------------------------------------------------- #
    def _v_pause(self, cmd: SteeringCommand) -> None:
        self.state.set_paused(True); self._emit(cmd, "applied", "paused")

    def _v_resume(self, cmd: SteeringCommand) -> None:
        self.state.set_paused(False); self._emit(cmd, "applied", "resumed")

    def _v_halt_entries(self, cmd: SteeringCommand) -> None:
        self.state.set_entries_halted(True); self._emit(cmd, "applied", "entries halted")

    def _v_allow_entries(self, cmd: SteeringCommand) -> None:
        self.state.set_entries_halted(False); self._emit(cmd, "applied", "entries allowed")

    def _v_kill(self, cmd: SteeringCommand) -> None:
        self.state.set_paused(True)  # pause takes effect immediately, market open or not
        if self._market_open():
            n = self._flatten_all_now()
            self._emit(cmd, "executed", f"KILL: flattened {n} + paused")
        else:
            self.channel.queue_offhours(cmd)
            self._emit(cmd, "deferred", "KILL: paused now; flatten queued for next open")
        self._reconcile()

    # ---- approval / lock verbs ------------------------------------------- #
    def _v_approve(self, cmd: SteeringCommand) -> None:
        pid = int(cmd.args["id"])
        pa = self.state.approve(pid)
        if pa is None:
            self._emit(cmd, "rejected", f"no pending approval #{pid}")
            return
        if not self._market_open():
            self._emit(cmd, "deferred", f"approved #{pid}; market closed (will not auto-run)")
            self._reconcile()
            return
        outcome = self.executor.execute_decision(pa.decision)
        self._emit(cmd, outcome.status, f"approved #{pid}: {outcome.detail}")
        self._reconcile()

    def _v_reject(self, cmd: SteeringCommand) -> None:
        pid = int(cmd.args["id"])
        pa, status = self.state.reject(pid, str(cmd.args.get("reason", "")))
        if pa is None:
            self._emit(cmd, "rejected", f"no pending approval #{pid}")
            return
        self._emit(cmd, "applied", f"rejected #{pid} -> {status}")
        self._reconcile()

    def _v_unlock(self, cmd: SteeringCommand) -> None:
        sym = str(cmd.args["symbol"]).upper()
        resolved = self.state.unlock_symbol(sym)
        extra = f"; resolved {len(resolved)} pending" if resolved else ""
        self._emit(cmd, "applied", f"unlocked {sym}{extra}")
        self._reconcile()

    def _v_cancel(self, cmd: SteeringCommand) -> None:
        sym = str(cmd.args["symbol"]).upper()
        opens = self.broker.get_open_orders(sym)
        if not opens:
            self._emit(cmd, "no_order", f"no open orders for {sym}")
            return
        for o in opens:
            self.broker.cancel_order(o.order_id)
        self._emit(cmd, "applied",
                   f"cancelled {len(opens)} orders for {sym} (protection removed; polled exit backup remains)")

    # ---- context verbs ---------------------------------------------------- #
    def _v_note(self, cmd: SteeringCommand) -> None:
        # logged only; surfaces at the next scheduled turn, no reconcile (Q7=A)
        self._emit(cmd, "applied", str(cmd.args.get("text", "")))

    def _v_directive(self, cmd: SteeringCommand) -> None:
        d = self.state.add_directive(str(cmd.args.get("text", "")))
        self._emit(cmd, "applied", f"directive {d.id} registered")
        self._reconcile()

    def _v_directive_clear(self, cmd: SteeringCommand) -> None:
        which = str(cmd.args.get("id") or cmd.args.get("which", "all"))
        n = self.state.clear_directive(which)
        self._emit(cmd, "applied", f"cleared {n} directive(s)")

    def _v_answer(self, cmd: SteeringCommand) -> None:
        # FR-7: the AgentQuestion answer store + agent feedback is wired in step 9;
        # here we record the answer and reconcile so the agent picks it up.
        self._emit(cmd, "applied", f"answered question {cmd.args.get('id', '')}")
        self._reconcile()

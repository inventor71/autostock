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
from src.agent.steering.records import InterventionRecord, PlaceOrderArgs, SteeringCommand
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
    # F9 structured verbs
    "place_order": "trade", "cancel_order": "lifecycle", "cancel_all": "lifecycle",
    "replace_order": "trade", "close_position": "trade", "close_all": "trade",
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
        # One visible line per handled command (no token — SECURITY-03). The poll/
        # snapshot ticks stay silent; this is the audit-worthy "a command did something".
        logger.info("steering: {} {} -> {}{}", cmd.verb, cmd.id[:8], outcome,
                    f" ({detail})" if detail else "")
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
        # F9 (critic fix): the shorthand BUY now passes the SAME human-order gate
        # as place_order — budget/pool/breaker were previously bypassed here.
        self._submit_gated(cmd, sym, order, price, atr, bool(cmd.args.get("force", False)))

    # ---- F9 structured order verbs --------------------------------------- #
    def _reject_detail(self, decision) -> str:
        """One-line reject string for an OrderDecision (token-free, SECURITY-03)."""
        bits = [decision.reason_code or "rejected"]
        if decision.message:
            bits.append(decision.message)
        if decision.suggestion:
            bits.append(f"try {decision.suggestion}")
        return " — ".join(bits)

    def _submit_gated(self, cmd: SteeringCommand, sym: str, order: Order,
                      price: float | None, atr: float | None, force: bool) -> None:
        """Run an Order through RiskManager.receive_human_order, then submit or
        emit a structured reject. Shared by /buy shorthand and place_order."""
        decision = self.risk_manager.receive_human_order(
            order, self.broker.get_portfolio_state(), price, atr=atr, force=force)
        if not decision.accepted:
            self._emit(cmd, "rejected", self._reject_detail(decision))
            return
        out = decision.order
        self.broker.submit_order(out)
        self.state.lock_symbol(sym)
        bracket = " (bracket)" if out.order_class == OrderClass.BRACKET else ""
        tag = f" [{decision.reason_code}]" if decision.reason_code else ""
        self._emit(cmd, "executed",
                   f"{out.side.value.upper()} {out.qty:g} {sym}{bracket}{tag}")
        self._reconcile()

    def _v_place_order(self, cmd: SteeringCommand) -> None:
        try:
            args = PlaceOrderArgs.model_validate(cmd.args)
        except Exception as e:
            self._emit(cmd, "rejected", f"bad place_order args: {e}")
            return
        sym = args.symbol.upper()
        if not self._market_open():
            self.channel.queue_offhours(cmd)
            self._emit(cmd, "deferred", "market closed; queued for next open")
            return
        price = self.data_provider.get_latest_price(sym)
        try:
            order = self._order_from_place_args(args, price)
        except ValueError as e:
            self._emit(cmd, "rejected", str(e))
            return
        atr = self.executor._atr(sym)
        self._submit_gated(cmd, sym, order, price, atr, args.force)

    def _order_from_place_args(self, args: PlaceOrderArgs, price: float | None) -> Order:
        """Resolve PlaceOrderArgs to a domain Order (notional->shares; legs).

        Raises ValueError (-> structured reject) on FR-7 violations or an
        unresolvable size. order_type/TIF/class validity beyond this is enforced
        by the Order validator and the RiskManager capability gate.
        """
        # FR-7: notional only for market+day; mutually exclusive with qty.
        if args.notional is not None:
            if args.qty is not None:
                raise ValueError("specify either qty or notional, not both")
            if args.order_type != "market" or args.time_in_force != "day":
                raise ValueError("notional is only allowed for market + day orders (FR-7)")
            if price is None or price <= 0:
                raise ValueError(f"no price to size notional for {args.symbol}")
            qty = math.floor(args.notional / price)
        elif args.qty is not None:
            qty = math.floor(args.qty)  # whole shares (Alpaca rejects fractional bracket legs)
        else:
            raise ValueError("qty or notional required")
        if qty <= 0:
            raise ValueError("size rounds to 0 shares")

        order_class = OrderClass(args.order_class)
        # take_profit/stop_loss imply a bracket when class left simple (Alpaca semantics).
        if order_class == OrderClass.SIMPLE and (args.take_profit is not None or args.stop_loss is not None):
            order_class = OrderClass.BRACKET

        return Order(
            symbol=args.symbol.upper(),
            side=OrderSide(args.side),
            qty=float(qty),
            order_type=OrderType(args.order_type),
            limit_price=args.limit_price,
            stop_price=args.stop_price,
            trail_price=args.trail_price,
            trail_percent=args.trail_percent,
            time_in_force=args.time_in_force,
            extended_hours=args.extended_hours,
            client_order_id=args.client_order_id,
            order_class=order_class,
            take_profit_price=args.take_profit,
            stop_loss_price=args.stop_loss,
        )

    def _v_cancel_order(self, cmd: SteeringCommand) -> None:
        oid = str(cmd.args.get("order_id", "")).strip()
        if not oid:
            self._emit(cmd, "no_order", "order_id required")
            return
        ok = self.broker.cancel_order(oid)
        self._emit(cmd, "applied" if ok else "no_order",
                   f"cancel order {oid}" if ok else f"could not cancel {oid}")

    def _v_cancel_all(self, cmd: SteeringCommand) -> None:
        sym = cmd.args.get("symbol")
        sym = str(sym).upper() if sym else None
        n = self.broker.cancel_all_orders(sym)
        scope = f" for {sym}" if sym else ""
        self._emit(cmd, "applied", f"cancelled {n} orders{scope}")

    def _v_replace_order(self, cmd: SteeringCommand) -> None:
        oid = str(cmd.args.get("order_id", "")).strip()
        if not oid:
            self._emit(cmd, "no_order", "order_id required")
            return
        changes = {k: cmd.args[k] for k in
                   ("qty", "limit_price", "stop_price", "trail", "time_in_force")
                   if cmd.args.get(k) is not None}
        # Q2=A: leg-aware replace is deferred; the broker (Alpaca) rejects a
        # bracket/OCO-leg replace, which surfaces here as a failure with guidance.
        filled = self.broker.replace_order(oid, changes)
        if filled is None:
            self._emit(cmd, "no_order",
                       f"replace failed for {oid} (bracket/OCO legs can't be replaced — "
                       f"cancel and re-place instead)")
            return
        self._emit(cmd, "applied", f"replaced {oid} -> {filled.order_id}")
        self._reconcile()

    def _v_close_position(self, cmd: SteeringCommand) -> None:
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
        self._emit(cmd, "executed", f"closed {sym}")
        self._reconcile()

    def _v_close_all(self, cmd: SteeringCommand) -> None:
        if not self._market_open():
            self.channel.queue_offhours(cmd)
            self._emit(cmd, "deferred", "market closed; queued for next open")
            return
        n = self._flatten_all_now()
        self._emit(cmd, "executed", f"closed {n} positions")
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
        price = float(cmd.args["price"])
        if not self._market_open():
            self.channel.queue_offhours(cmd)
            self._emit(cmd, "deferred", "market closed; queued for next open")
            return
        # review #7: a long's protective stop must be BELOW the market, else it triggers
        # an immediate exit. Reject a fat-fingered stop at/above market instead of placing it.
        pos = self.broker.get_position(sym)
        if pos is not None and pos.qty > 0:
            try:
                mkt = self.data_provider.get_latest_price(sym)
            except Exception:
                mkt = None
            if mkt and price >= mkt:
                self._emit(cmd, "no_order",
                           f"stop {price} >= market {mkt:.2f} for long {sym}; would exit immediately")
                return
        outcome = self.executor.execute_decision(
            Decision(symbol=sym, action="ADJUST_STOP", source="human", stop=price))
        self._emit(cmd, outcome.status, outcome.detail or f"stop {sym} -> {price}")
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
        # The arg is a SYMBOL (cancel its resting protective orders) OR a queued off-hours
        # trade id / id-PREFIX (the sidebar shows an 8-char id). Resolve here so the operator
        # can paste the short id: a UNIQUE queued-id prefix wins; otherwise it's a symbol.
        target = str(cmd.args.get("target") or cmd.args.get("queued_id")
                     or cmd.args.get("symbol") or "").strip()
        pref = target.lower()
        if pref:
            matches = [c for c in self.channel.list_offhours() if c.id.startswith(pref)]
            if len(matches) > 1:
                self._emit(cmd, "no_order",
                           f"ambiguous queued-id prefix '{target}' ({len(matches)} matches)")
                return
            if len(matches) == 1:
                self.channel.remove_offhours(matches[0].id)
                self._emit(cmd, "applied", f"cancelled queued trade {matches[0].id[:8]}")
                return
        sym = target.upper()
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
        # FR-7: persist the answer to a SEPARATE append-only file (never rewrite the
        # agent-written questions file -- critic #7); the reconcile turn surfaces it.
        from src.agent.steering.jsonl import read_complete_lines
        from src.agent.steering.records import AgentAnswer, AgentQuestion

        qid = str(cmd.args.get("id", ""))
        # review #1: validate the id against the agent's open questions. Without this,
        # a mistyped/abbreviated id was accepted, the answer orphaned (never joins a
        # real uuid-hex question), and a false "applied" success was reported.
        known: set[str] = set()
        lines, _ = read_complete_lines(self.journal.root / "agent_questions.jsonl", 0)
        for line in lines:
            try:
                known.add(AgentQuestion.model_validate_json(line).id)
            except Exception:
                continue
        if qid not in known:
            self._emit(cmd, "rejected", f"unknown question id {qid!r} (no matching open question)")
            return
        ans = AgentAnswer(question_id=qid, text=str(cmd.args.get("text", "")))
        path = self.journal.root / "agent_answers.jsonl"
        self.journal.root.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(ans.model_dump_json() + "\n")
        self._emit(cmd, "applied", f"answered question {qid}")
        self._reconcile()

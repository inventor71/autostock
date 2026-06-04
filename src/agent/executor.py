"""Decision executor: the bridge from the agent's journal to the broker.

Reads new lines from ``decisions.jsonl`` and runs each through the SAME
deterministic gate as every other path -- ``RiskManager`` (with bracket orders
enabled) then the broker. The agent is advisory only; this module is the only
thing that places orders, and it applies the pool constraint, decision expiry,
the circuit breaker, and resting-protection reconciliation.

A cursor in the workspace records how many decision lines have been processed,
so re-running is idempotent (a resting bracket is submitted once; the exchange
then holds it).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from loguru import logger

from src.agent.journal import Decision, Journal
from src.agent.steering.jsonl import atomic_write_text
from src.agent.tools import market
from src.core.models import Order, TradeSignal
from src.core.types import OrderClass, OrderSide, OrderType, PositionSide, Signal
from src.risk.exits import run_polled_exits


@dataclass
class ExecutionOutcome:
    decision: Decision
    status: str  # executed | skipped_* | no_order | error
    detail: str = ""
    order_id: str | None = None


def _now_like(dt: datetime) -> datetime:
    """Now in the same naive/aware-ness as ``dt`` (so comparison never raises)."""
    return datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()


class DecisionExecutor:
    def __init__(
        self,
        broker,
        risk_manager,
        data_provider,
        journal: Journal | None = None,
        *,
        universe: list[str],
    ):
        # The agent path REQUIRES a RiskManager constructed with bracket-mode
        # enabled — it builds resting brackets from the agent's levels. Validate
        # explicitly instead of silently flipping a flag on the injected object.
        if not risk_manager.use_bracket_orders:
            raise ValueError(
                "DecisionExecutor requires a RiskManager constructed with "
                "use_bracket_orders=True"
            )
        self.broker = broker
        self.risk_manager = risk_manager
        self.data_provider = data_provider
        self.journal = journal or Journal()
        self.universe = {s.upper() for s in universe}
        self._state_file = self.journal.root / ".executor_state.json"

    # ------------------------------------------------------------------ #
    # Cursor (idempotency)
    # ------------------------------------------------------------------ #
    def _load_cursor(self) -> tuple[int, set[int]]:
        """Return (cursor, terminal_indices). Terminal indices are permanently
        resolved (executed or legitimately skipped) and never re-processed.
        Backward-compat: old state files without ``terminal_indices`` default to
        an empty set so the first run with new code re-processes all pending
        indices — safe, since the old code already unconditionally advanced past
        them."""
        if self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text())
                cursor = int(data.get("cursor", 0))
                terminal_indices = set(data.get("terminal_indices", []))
                return cursor, terminal_indices
            except Exception:
                return 0, set()
        return 0, set()

    def _save_cursor(self, cursor: int, terminal_indices: set[int]) -> None:
        # Atomic (temp + os.replace): with the F4 single CommandWorker now the
        # sole writer, a torn cursor file can never be observed (BR-7.1' / critic #2).
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            self._state_file,
            json.dumps({
                "cursor": cursor,
                "terminal_indices": sorted(terminal_indices),
                "updated_at": datetime.now().isoformat(),
            }),
        )

    # ------------------------------------------------------------------ #
    # Execution log (F24: durable decision→fill link for quality metrics)
    # ------------------------------------------------------------------ #
    def _log_execution(self, d: Decision, filled, *, decision_index: int = -1) -> None:
        log_file = self.journal.root / "execution_log.jsonl"
        try:
            entry = json.dumps({
                "decision_index": decision_index,
                "symbol": d.symbol,
                "action": d.action,
                "order_id": filled.order_id,
                "filled_qty": float(filled.qty),
                "filled_price": float(filled.filled_price),
                "ts": d.ts.isoformat(),
            })
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8") as fh:
                fh.write(entry + "\n")
        except Exception as exc:
            logger.warning(f"execution_log append failed (non-fatal): {exc}")

    def _log_outcome(self, outcome: ExecutionOutcome, *, decision_index: int = -1) -> None:
        """Persist EVERY outcome (all statuses) to ``execution_outcomes.jsonl``
        so failures leave a durable audit trail — unlike the old behaviour where
        only ``"executed"`` was recorded (in ``execution_log.jsonl``)."""
        log_file = self.journal.root / "execution_outcomes.jsonl"
        try:
            entry = json.dumps({
                "decision_index": decision_index,
                "symbol": outcome.decision.symbol,
                "action": outcome.decision.action,
                "status": outcome.status,
                "detail": outcome.detail,
                "order_id": outcome.order_id,
                "ts": outcome.decision.ts.isoformat(),
            })
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8") as fh:
                fh.write(entry + "\n")
        except Exception as exc:
            logger.warning(f"execution_outcomes append failed (non-fatal): {exc}")

    # ------------------------------------------------------------------ #
    # Execute pending decisions
    # ------------------------------------------------------------------ #
    def execute_pending(self) -> list[ExecutionOutcome]:
        # Trade only during the regular session; off-hours, leave decisions
        # pending (cursor untouched) so they execute at the next open.
        if not self.broker.is_market_open():
            logger.info("Market closed; deferring decision execution")
            return []

        decisions = self.journal.read_decisions()
        cursor, terminal_indices = self._load_cursor()
        pending = decisions[cursor:]
        if not pending:
            return []

        # Collapse multiple decisions for the same symbol in this batch to the
        # latest one — a later call supersedes earlier ones. This prevents e.g.
        # two HOLDs for one name placing a protective order and then immediately
        # trying to replace it within a single cycle. Track the original index
        # for the execution log (F24: decision→fill linkage).
        latest_by_symbol: dict[str, tuple[int, Decision]] = {}
        for i, d in enumerate(pending):
            latest_by_symbol[d.symbol] = (cursor + i, d)
        batch: list[tuple[int, Decision]] = list(latest_by_symbol.values())

        # Filter out already-terminal indices (idempotency: never re-execute a
        # decision that was already resolved on a previous cycle).
        active_batch = [(idx, d) for idx, d in batch if idx not in terminal_indices]

        self._update_market_halt()

        # Statuses that permanently resolve a decision — the cursor may safely
        # advance past them. "no_order" and "error" are retryable: the cursor
        # stops before them so they are re-processed next cycle.
        _TERMINAL = frozenset({
            "executed", "skipped_hold", "skipped_out_of_universe", "skipped_expired",
        })

        outcomes: list[ExecutionOutcome] = []
        for idx, d in active_batch:
            try:
                outcome = self.execute_decision(d, decision_index=idx)
            except Exception as e:
                logger.error(f"Execution error for {d.symbol} {d.action}: {e}")
                outcome = ExecutionOutcome(d, "error", str(e))
            outcomes.append(outcome)
            # Persist EVERY outcome — durable audit trail for failures.
            self._log_outcome(outcome, decision_index=idx)
            if outcome.status in _TERMINAL:
                terminal_indices.add(idx)

        # Advance cursor past a contiguous prefix of terminal indices.
        new_cursor = len(decisions)
        for i in range(cursor, len(decisions)):
            if i not in terminal_indices:
                new_cursor = i
                break

        self._save_cursor(new_cursor, terminal_indices)
        return outcomes

    def execute_decision(self, d: Decision, *, decision_index: int = -1) -> ExecutionOutcome:
        """Run ONE decision through the gate (universe/expiry/HOLD/ADJUST_STOP or
        RiskManager->Broker). Cursor-free and reads no journal file, so it is the
        single-decision entry point shared by ``execute_pending`` (agent batch),
        a human-forced trade, and an approved-pending execution (F4).

        WARNING: this method does NOT check ``is_market_open()`` -- it will submit
        to the broker unconditionally. ``execute_pending`` gates above before
        calling it; any OTHER caller (the F4 command worker for human trades /
        approvals) MUST itself check ``broker.is_market_open()`` and, off-hours,
        queue the trade for the next open instead of calling this (BR-2.7). A
        human command is consumed once, so it cannot "defer by leaving the cursor"
        the way the agent batch does."""
        if d.symbol not in self.universe:
            logger.warning(f"Rejecting out-of-universe decision: {d.symbol} {d.action}")
            return ExecutionOutcome(d, "skipped_out_of_universe")

        if d.valid_until is not None and d.valid_until < _now_like(d.valid_until):
            return ExecutionOutcome(d, "skipped_expired", f"valid_until {d.valid_until}")

        if d.action == "HOLD":
            # The agent expresses "keep holding, protected at this stop" as
            # HOLD + stop. Honour it: ensure a resting protective order at that
            # stop/target on the held position (otherwise the stop is never
            # placed and only the polled 5% backup covers it).
            if d.stop is not None and self.broker.get_position(d.symbol) is not None:
                return self._place_protection(d, label="protect")
            return ExecutionOutcome(d, "skipped_hold")

        if d.action == "ADJUST_STOP":
            return self._adjust_stop(d)

        # BUY / SELL / SELL_SHORT / BUY_TO_COVER -> RiskManager -> broker
        portfolio = self.broker.get_portfolio_state()
        try:
            price = self.data_provider.get_latest_price(d.symbol)
        except Exception as e:
            return ExecutionOutcome(d, "error", f"price fetch failed: {e}")

        # F54 auto-flip (BR-6): a directional reversal closes the opposite-side
        # position FIRST, all-or-nothing. SELL_SHORT over a long → close long
        # then short; BUY over a short → cover then go long. The close failing
        # aborts the new entry so the book never ends in an ambiguous state.
        existing = portfolio.positions.get(d.symbol)
        if existing is not None:
            flip = self._maybe_flip(d, existing, price)
            if flip is not None:
                if flip.status != "executed":
                    return flip  # close failed → abort, don't open the new side
                # Re-snapshot: the closed position is gone now.
                portfolio = self.broker.get_portfolio_state()

        signal = self._to_signal(d)
        order = self.risk_manager.evaluate_signal(signal, price, portfolio)
        if order is None:
            return ExecutionOutcome(d, "no_order", "risk manager returned no order")

        filled = self.broker.submit_order(order)
        outcome = ExecutionOutcome(
            d, "executed",
            f"{order.side.value} {order.qty} {d.symbol} ({order.order_class.value})",
            order_id=filled.order_id,
        )
        self._log_execution(d, filled, decision_index=decision_index)
        return outcome

    def _maybe_flip(self, d: Decision, existing, price: float) -> ExecutionOutcome | None:
        """If decision ``d`` reverses an existing position's direction, close that
        position first. Returns the close ExecutionOutcome (executed/error), or
        None when no flip is needed. Cancels any resting protection before the
        close so its qty is released."""
        long_to_short = d.action == "SELL_SHORT" and existing.side == PositionSide.LONG
        short_to_long = d.action == "BUY" and existing.side == PositionSide.SHORT
        if not (long_to_short or short_to_long):
            return None

        # Release resting protective legs so the close isn't short of qty.
        opens = self.broker.get_open_orders(d.symbol)
        if opens:
            self._cancel_and_wait(d.symbol, opens)

        closed = self.broker.close_position(d.symbol)
        # Do NOT trust close_position's reported qty for the all-or-nothing gate:
        # AlpacaBroker.close_position falls back to the *requested* qty when the
        # async close hasn't filled within the poll window (alpaca_broker.py), so
        # a non-terminal close would look "executed". The authoritative check is
        # the position itself — it must be flat before we open the opposite side.
        # Otherwise we'd be long+short the same name with protection already
        # cancelled and the new bracket sized off a stale snapshot.
        if self.broker.get_position(d.symbol) is not None:
            logger.error(
                f"Auto-flip aborted for {d.symbol}: {existing.side.value} position "
                f"not flat after close (partial/pending fill) — NOT opening opposite side"
            )
            return ExecutionOutcome(
                d, "error",
                f"auto-flip: existing {existing.side.value} position did not close flat",
            )
        closed_qty = closed.qty if closed is not None else 0.0
        logger.info(
            f"Auto-flip {d.symbol}: closed {existing.side.value} "
            f"{closed_qty} @ {closed.filled_price if closed else 0:.2f}, opening opposite side"
        )
        outcome = ExecutionOutcome(
            d, "executed",
            f"auto-flip close {existing.side.value} {closed_qty} {d.symbol}",
            order_id=closed.order_id if closed else None,
        )
        # Durable audit for the close leg (both logs), so the flip is fully traced
        # and not silently folded into the new entry's outcome (critic #6).
        if closed is not None:
            self._log_execution(d, closed)
        self._log_outcome(outcome)
        return outcome

    def _to_signal(self, d: Decision) -> TradeSignal:
        confidence = d.confidence if d.confidence is not None else 0.5
        # Entries (BUY / SELL_SHORT) carry the LLM's key levels + an ATR fallback
        # so RiskManager can build a (correctly-oriented) bracket. The level keys
        # are direction-neutral; RiskManager interprets them per side.
        if d.action in ("BUY", "SELL_SHORT"):
            metadata: dict[str, Any] = {
                "key_levels": {"entry": d.limit, "stop_loss": d.stop, "take_profit": d.target}
            }
            atr = self._atr(d.symbol)
            if atr is not None:
                metadata["atr"] = atr  # lets RiskManager fall back to an ATR stop
            # SELL_SHORT carries prev_close so RiskManager's individual-stock
            # squeeze guard (reject a short into a name already up >=N% today) has
            # the data it needs — without it the guard is dead (critic #3).
            if d.action == "SELL_SHORT":
                prev_close = self._prev_close(d.symbol)
                if prev_close is not None:
                    metadata["prev_close"] = prev_close
            sig = Signal.BUY if d.action == "BUY" else Signal.SELL_SHORT
            return TradeSignal(symbol=d.symbol, signal=sig, confidence=confidence, metadata=metadata)
        # Exits (SELL / BUY_TO_COVER) carry the partial fraction.
        sig = Signal.BUY_TO_COVER if d.action == "BUY_TO_COVER" else Signal.SELL
        return TradeSignal(
            symbol=d.symbol, signal=sig, confidence=confidence,
            sell_pct=d.sell_pct if d.sell_pct is not None else 1.0,
        )

    def _atr(self, symbol: str) -> float | None:
        try:
            return market.indicators(symbol, self.data_provider).get("atr_abs")
        except Exception:
            return None

    def _prev_close(self, symbol: str) -> float | None:
        """Yesterday's close, for the short squeeze-guard day-change. Best-effort:
        any failure → None (guard simply doesn't fire, never blocks on data)."""
        try:
            bars = self.data_provider.get_bars(symbol, limit=2)
            if bars is not None and len(bars) >= 2:
                return float(bars["close"].iloc[-2])
        except Exception:
            pass
        return None

    def _adjust_stop(self, d: Decision) -> ExecutionOutcome:
        if self.broker.get_position(d.symbol) is None:
            return ExecutionOutcome(d, "no_order", "no position to adjust")
        if d.stop is None:
            return ExecutionOutcome(d, "no_order", "ADJUST_STOP without a stop level")
        return self._place_protection(d, label="ADJUST_STOP")

    def _place_protection(self, d: Decision, label: str) -> ExecutionOutcome:
        """Ensure a resting protective order at the (ratcheted) stop on a held
        position, keeping the decision's target (or the existing one). Idempotent:
        skips when protection already rests at that stop/target so HOLD turns
        don't churn the book."""
        position = self.broker.get_position(d.symbol)
        if position is None:
            return ExecutionOutcome(d, "no_order", "no position to protect")

        # F54: a long is protected by SELL legs (ratchet UP); a short by
        # BUY_TO_COVER legs (ratchet DOWN). The protective side + ratchet
        # direction both follow the position's side.
        is_short = position.side == PositionSide.SHORT
        protective_side = OrderSide.BUY_TO_COVER if is_short else OrderSide.SELL

        opens = self.broker.get_open_orders(d.symbol)
        current_stop = next((o.stop_price for o in opens if o.stop_price is not None), None)
        current_target = next(
            (o.limit_price for o in opens
             if o.limit_price is not None and o.side == protective_side),
            None,
        )
        new_stop = self.risk_manager.ratchet_stop(
            current_stop if current_stop is not None else d.stop, d.stop,
            position_side=position.side,
        )
        target = d.target if d.target is not None else current_target

        already = (
            current_stop is not None
            and abs(current_stop - new_stop) < 0.01
            and (target is None or (current_target is not None and abs(current_target - target) < 0.01))
        )
        if already:
            return ExecutionOutcome(d, "skipped_hold", "already protected at this stop")

        self._cancel_and_wait(d.symbol, opens)

        if target is not None:
            order = Order(
                symbol=d.symbol, side=protective_side, qty=position.qty,
                order_class=OrderClass.OCO, take_profit_price=target, stop_loss_price=new_stop,
            )
        else:
            order = Order(
                symbol=d.symbol, side=protective_side, qty=position.qty,
                order_type=OrderType.STOP, stop_price=new_stop,
            )
        filled = self.broker.submit_order(order)
        detail = f"{label} {d.symbol} ({position.side.value}) stop->{new_stop:.2f}"
        if target is not None:
            detail += f" target {target:.2f}"
        return ExecutionOutcome(d, "executed", detail, order_id=filled.order_id)

    def _cancel_and_wait(self, symbol: str, opens, timeout: float = 6.0, interval: float = 0.5) -> None:
        """Cancel the given orders, then wait for the broker to release the held
        qty before a replacement is submitted. Alpaca cancellation is async, so
        re-submitting immediately fails with 'insufficient qty available'."""
        for o in opens:
            self.broker.cancel_order(o.order_id)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.broker.get_open_orders(symbol):
                return
            time.sleep(interval)

    # ------------------------------------------------------------------ #
    # Reconciliation helpers
    # ------------------------------------------------------------------ #
    def _update_market_halt(self) -> None:
        """Feed SPY's day-change to the circuit breaker (fail-open on error)."""
        try:
            bars = self.data_provider.get_bars("SPY", limit=2)
            if bars is not None and len(bars) >= 2:
                change = bars["close"].iloc[-1] / bars["close"].iloc[-2] - 1
                self.risk_manager.update_market_halt(float(change))
        except Exception as e:
            logger.debug(f"Market-halt update skipped: {e}")

    def protected_symbols(self) -> set[str]:
        """Symbols that already have a resting order (skip in polled backups)."""
        try:
            return {o.symbol.upper() for o in self.broker.get_open_orders()}
        except Exception:
            return set()

    def run_risk_exits(self) -> list:
        """Polled stop/take-profit backup for positions WITHOUT resting protection.

        Market-hours gated (off-hours the bracket order at the exchange is the
        sole line of defense); see ``src/risk/exits.py`` for the shared logic.
        """
        if not self.broker.is_market_open():
            return []
        return run_polled_exits(
            self.risk_manager, self.broker, self.broker.get_portfolio_state(),
            data_provider=self.data_provider,
            protected_symbols=self.protected_symbols(),
        )

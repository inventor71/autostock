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
from src.agent.tools import market
from src.core.models import Order, TradeSignal
from src.core.types import OrderClass, OrderSide, OrderType, Signal


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
        self.broker = broker
        self.risk_manager = risk_manager
        # The agent path trades via resting brackets built from its levels.
        self.risk_manager.use_bracket_orders = True
        self.data_provider = data_provider
        self.journal = journal or Journal()
        self.universe = {s.upper() for s in universe}
        self._state_file = self.journal.root / ".executor_state.json"

    # ------------------------------------------------------------------ #
    # Cursor (idempotency)
    # ------------------------------------------------------------------ #
    def _load_cursor(self) -> int:
        if self._state_file.exists():
            try:
                return int(json.loads(self._state_file.read_text()).get("cursor", 0))
            except Exception:
                return 0
        return 0

    def _save_cursor(self, n: int) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(
            json.dumps({"cursor": n, "updated_at": datetime.now().isoformat()})
        )

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
        cursor = self._load_cursor()
        pending = decisions[cursor:]
        if not pending:
            return []

        # Collapse multiple decisions for the same symbol in this batch to the
        # latest one — a later call supersedes earlier ones. This prevents e.g.
        # two HOLDs for one name placing a protective order and then immediately
        # trying to replace it within a single cycle.
        latest_by_symbol: dict[str, Decision] = {}
        for d in pending:
            latest_by_symbol[d.symbol] = d
        batch = list(latest_by_symbol.values())

        self._update_market_halt()

        outcomes: list[ExecutionOutcome] = []
        for d in batch:
            try:
                outcomes.append(self._execute_one(d))
            except Exception as e:
                logger.error(f"Execution error for {d.symbol} {d.action}: {e}")
                outcomes.append(ExecutionOutcome(d, "error", str(e)))
        self._save_cursor(len(decisions))
        return outcomes

    def _execute_one(self, d: Decision) -> ExecutionOutcome:
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

        # BUY / SELL -> RiskManager -> broker
        portfolio = self.broker.get_portfolio_state()
        try:
            price = self.data_provider.get_latest_price(d.symbol)
        except Exception as e:
            return ExecutionOutcome(d, "error", f"price fetch failed: {e}")

        signal = self._to_signal(d)
        order = self.risk_manager.evaluate_signal(signal, price, portfolio)
        if order is None:
            return ExecutionOutcome(d, "no_order", "risk manager returned no order")

        filled = self.broker.submit_order(order)
        return ExecutionOutcome(
            d, "executed",
            f"{order.side.value} {order.qty} {d.symbol} ({order.order_class.value})",
            order_id=filled.order_id,
        )

    def _to_signal(self, d: Decision) -> TradeSignal:
        confidence = d.confidence if d.confidence is not None else 0.5
        if d.action == "BUY":
            metadata: dict[str, Any] = {
                "key_levels": {"entry": d.limit, "stop_loss": d.stop, "take_profit": d.target}
            }
            atr = self._atr(d.symbol)
            if atr is not None:
                metadata["atr"] = atr  # lets RiskManager fall back to an ATR stop
            return TradeSignal(symbol=d.symbol, signal=Signal.BUY, confidence=confidence, metadata=metadata)
        return TradeSignal(
            symbol=d.symbol, signal=Signal.SELL, confidence=confidence,
            sell_pct=d.sell_pct if d.sell_pct is not None else 1.0,
        )

    def _atr(self, symbol: str) -> float | None:
        try:
            return market.indicators(symbol, self.data_provider).get("atr_abs")
        except Exception:
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

        opens = self.broker.get_open_orders(d.symbol)
        current_stop = next((o.stop_price for o in opens if o.stop_price is not None), None)
        current_target = next(
            (o.limit_price for o in opens if o.limit_price is not None and o.side == OrderSide.SELL),
            None,
        )
        # Ratchet: only tighten (raise) the long stop unless widening is intended.
        new_stop = self.risk_manager.ratchet_stop(
            current_stop if current_stop is not None else d.stop, d.stop
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
                symbol=d.symbol, side=OrderSide.SELL, qty=position.qty,
                order_class=OrderClass.OCO, take_profit_price=target, stop_loss_price=new_stop,
            )
        else:
            order = Order(
                symbol=d.symbol, side=OrderSide.SELL, qty=position.qty,
                order_type=OrderType.STOP, stop_price=new_stop,
            )
        filled = self.broker.submit_order(order)
        detail = f"{label} {d.symbol} stop->{new_stop:.2f}"
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
        """Polled stop/take-profit backup for positions WITHOUT resting protection."""
        if not self.broker.is_market_open():
            return []
        portfolio = self.broker.get_portfolio_state()
        for sym, pos in portfolio.positions.items():
            try:
                pos.update_price(self.data_provider.get_latest_price(sym))
            except Exception:
                pass
        protected = self.protected_symbols()
        filled = []
        exits = (
            self.risk_manager.check_stop_loss(portfolio, protected)
            + self.risk_manager.check_take_profit(portfolio, protected)
        )
        for order in exits:
            try:
                filled.append(self.broker.submit_order(order))
            except Exception as e:
                logger.error(f"Backup exit failed for {order.symbol}: {e}")
        return filled

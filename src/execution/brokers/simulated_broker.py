from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from loguru import logger

from src.core.models import FilledOrder, OpenOrder, Order, Position, PortfolioState
from src.core.types import OrderClass, OrderSide, OrderType, PositionSide
from src.core.exceptions import BrokerError
from src.execution.base import BaseBroker


@dataclass
class _RestingLeg:
    """A resting order leg held by the simulated exchange until price triggers it."""

    leg_id: str
    symbol: str
    side: OrderSide
    qty: float
    kind: str  # "limit" | "stop"
    trigger_price: float
    role: str  # "entry" | "take_profit" | "stop_loss"
    group: str | None = None  # OCO group: filling one leg cancels its siblings
    # For an entry leg, the protection to arm once the entry fills:
    bracket: dict | None = None  # {"take_profit_price": float, "stop_loss_price": float}


class SimulatedBroker(BaseBroker):
    """Simulated broker for backtesting.

    Simple (market) orders fill immediately at the current price. Bracket / OCO
    orders register **resting legs** that trigger on price like a real exchange:
    a take-profit LIMIT fills when the bar high crosses it, a stop-loss STOP
    fills when the bar low crosses it, and filling one cancels its OCO sibling.
    This keeps backtest/paper behaviour faithful to live resting protective
    orders (gap-safe, no polling), so the agent's stop/take levels are honoured
    the same way in simulation as at Alpaca.
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission_pct: float = 0.0,
    ):
        self._cash = initial_capital
        self._initial_capital = initial_capital
        self._positions: dict[str, Position] = {}
        self._commission_pct = commission_pct
        self._order_counter = 0
        self._group_counter = 0
        self._current_prices: dict[str, float] = {}
        # symbol -> resting legs awaiting a price trigger
        self._resting: dict[str, list[_RestingLeg]] = {}
        # order_id -> fill, so get_order_status can report resting-leg fills
        self._fills: dict[str, FilledOrder] = {}

    def set_current_price(
        self,
        symbol: str,
        price: float,
        high: float | None = None,
        low: float | None = None,
    ) -> list[FilledOrder]:
        """Set current price for simulated fills and trigger any resting legs.

        ``high``/``low`` let callers feed a bar's intrabar range so resting
        stops/limits trigger on the extreme rather than only the close; both
        default to ``price`` (close-only behaviour).

        Returns the fills from any resting legs the bar's range triggered (empty
        if none) so callers — e.g. the backtest engine — can record exits that
        the simulated exchange filled intra-bar.
        """
        self._current_prices[symbol] = price
        if symbol in self._positions:
            self._positions[symbol].update_price(price)
        return self._process_resting(
            symbol,
            high if high is not None else price,
            low if low is not None else price,
        )

    def submit_order(self, order: Order) -> FilledOrder:
        if order.order_class == OrderClass.BRACKET:
            return self._submit_bracket(order)
        if order.order_class == OrderClass.OCO:
            return self._submit_oco(order)

        # SIMPLE order: fill immediately at the current price.
        price = self._current_prices.get(order.symbol)
        if price is None:
            raise BrokerError(f"No price set for {order.symbol}")
        if order.side == OrderSide.BUY:
            return self._execute_buy(order.symbol, order.qty, price)
        if order.side == OrderSide.SELL_SHORT:
            return self._execute_sell_short(order.symbol, order.qty, price)
        if order.side == OrderSide.BUY_TO_COVER:
            return self._execute_buy_to_cover(order.symbol, order.qty, price)
        return self._execute_sell(order.symbol, order.qty, price)

    # ------------------------------------------------------------------ #
    # Bracket / OCO submission
    # ------------------------------------------------------------------ #
    def _submit_bracket(self, order: Order) -> FilledOrder:
        price = self._current_prices.get(order.symbol)
        protection = {
            "take_profit_price": order.take_profit_price,
            "stop_loss_price": order.stop_loss_price,
        }

        # F54: a short bracket's entry is SELL_SHORT, protection is BUY_TO_COVER.
        is_short = order.side == OrderSide.SELL_SHORT
        entry_side = OrderSide.SELL_SHORT if is_short else OrderSide.BUY

        if order.order_type == OrderType.LIMIT:
            # Resting entry: fills when price reaches the limit, then arms
            # protection. Evaluate against the current bar in case it fills now.
            leg = self._add_resting(
                order.symbol, entry_side, order.qty, "limit",
                order.limit_price, "entry", group=None, bracket=protection,
            )
            fills = (
                self._process_resting(order.symbol, price, price)
                if price is not None else []
            )
            entry = next((f for f in fills if f.side == entry_side), None)
            return entry or self._pending(leg.leg_id, order.symbol, entry_side)

        # Market entry: fill now, arm protection, then re-check the same bar so
        # a gap that blows through the entry and the stop still stops out.
        if price is None:
            raise BrokerError(f"No price set for {order.symbol}")
        if is_short:
            entry = self._execute_sell_short(order.symbol, order.qty, price)
        else:
            entry = self._execute_buy(order.symbol, order.qty, price)
        self._arm_protection(
            order.symbol, order.qty, order.take_profit_price,
            order.stop_loss_price, short=is_short,
        )
        self._process_resting(order.symbol, price, price)
        return entry

    def _submit_oco(self, order: Order) -> FilledOrder:
        # Attach protective legs to an existing position (no entry leg).
        pos = self._positions.get(order.symbol)
        if pos is None:
            raise BrokerError(f"No position for OCO on {order.symbol}")
        is_short = pos.side == PositionSide.SHORT
        protective_side = OrderSide.BUY_TO_COVER if is_short else OrderSide.SELL
        group = self._arm_protection(
            order.symbol, order.qty, order.take_profit_price,
            order.stop_loss_price, short=is_short,
        )
        price = self._current_prices.get(order.symbol)
        fills = self._process_resting(order.symbol, price, price) if price is not None else []
        return fills[0] if fills else self._pending(group, order.symbol, protective_side)

    def _arm_protection(
        self,
        symbol: str,
        qty: float,
        take_profit_price: float | None,
        stop_loss_price: float | None,
        short: bool = False,
    ) -> str:
        """Register an OCO protective pair; returns the group id. Long positions
        protect with SELL legs, shorts with BUY_TO_COVER legs (F54)."""
        self._group_counter += 1
        group = f"oco_{self._group_counter}"
        side = OrderSide.BUY_TO_COVER if short else OrderSide.SELL
        if take_profit_price is not None:
            self._add_resting(symbol, side, qty, "limit", take_profit_price, "take_profit", group)
        if stop_loss_price is not None:
            self._add_resting(symbol, side, qty, "stop", stop_loss_price, "stop_loss", group)
        return group

    def _add_resting(
        self,
        symbol: str,
        side: OrderSide,
        qty: float,
        kind: str,
        trigger_price: float,
        role: str,
        group: str | None,
        bracket: dict | None = None,
    ) -> _RestingLeg:
        self._order_counter += 1
        leg = _RestingLeg(
            leg_id=f"sim_resting_{self._order_counter}",
            symbol=symbol,
            side=side,
            qty=qty,
            kind=kind,
            trigger_price=trigger_price,
            role=role,
            group=group,
            bracket=bracket,
        )
        self._resting.setdefault(symbol, []).append(leg)
        return leg

    # ------------------------------------------------------------------ #
    # Resting-leg trigger evaluation
    # ------------------------------------------------------------------ #
    def _process_resting(self, symbol: str, high: float, low: float) -> list[FilledOrder]:
        """Trigger any resting legs the bar's range reaches; return their fills.

        Loops to a fixed point so an entry that fills can arm protection that
        also triggers within the same bar. Within an OCO pair the stop-loss is
        evaluated before the take-profit, so a bar straddling both stops out
        (the conservative outcome).
        """
        produced: list[FilledOrder] = []
        progressed = True
        while progressed:
            progressed = False
            legs = self._resting.get(symbol)
            if not legs:
                break
            # Stop-loss legs first so a both-sides bar resolves adversely.
            for leg in sorted(legs, key=lambda l: 0 if l.role == "stop_loss" else 1):
                if leg not in self._resting.get(symbol, []):
                    continue  # already removed by an OCO sibling fill
                if not self._is_triggered(leg, high, low):
                    continue
                fill = self._fill_leg(leg, high, low)
                if fill is not None:
                    produced.append(fill)
                progressed = True
                break  # restart the scan after mutating the book
        return produced

    @staticmethod
    def _is_triggered(leg: _RestingLeg, high: float, low: float) -> bool:
        # "sell-like" legs (SELL long-exit, SELL_SHORT short-entry) want the
        # higher price; "buy-like" legs (BUY long-entry, BUY_TO_COVER short-exit)
        # want the lower price.
        sell_like = leg.side in (OrderSide.SELL, OrderSide.SELL_SHORT)
        if leg.kind == "limit":
            # A favorable limit: sell-like fills on a rally, buy-like on a dip.
            return high >= leg.trigger_price if sell_like else low <= leg.trigger_price
        # An adverse stop breakout: sell-like fills on a drop, buy-like on a rip.
        return low <= leg.trigger_price if sell_like else high >= leg.trigger_price

    def _fill_leg(self, leg: _RestingLeg, high: float, low: float) -> FilledOrder | None:
        price = leg.trigger_price
        if leg.role == "entry":
            # Entry leg: BUY (long) or SELL_SHORT (short). Arm protection after.
            try:
                if leg.side == OrderSide.SELL_SHORT:
                    fill = self._execute_sell_short(leg.symbol, leg.qty, price)
                else:
                    fill = self._execute_buy(leg.symbol, leg.qty, price)
            except BrokerError:
                self._remove_leg(leg)  # e.g. insufficient cash -> drop the entry
                return None
            self._remove_leg(leg)
            if leg.bracket:
                self._arm_protection(
                    leg.symbol, leg.qty,
                    leg.bracket.get("take_profit_price"),
                    leg.bracket.get("stop_loss_price"),
                    short=(leg.side == OrderSide.SELL_SHORT),
                )
            return fill

        # Protective leg: SELL (long exit) or BUY_TO_COVER (short exit).
        pos = self._positions.get(leg.symbol)
        if pos is None:
            self._cancel_group(leg)  # position already gone
            return None
        qty = min(leg.qty, pos.qty)
        if leg.side == OrderSide.BUY_TO_COVER:
            fill = self._execute_buy_to_cover(leg.symbol, qty, price)
        else:
            fill = self._execute_sell(leg.symbol, qty, price)
        self._cancel_group(leg)  # OCO: filling one leg cancels its sibling
        return fill

    # ------------------------------------------------------------------ #
    # Position bookkeeping
    # ------------------------------------------------------------------ #
    def _execute_buy(self, symbol: str, qty: float, price: float) -> FilledOrder:
        cost = price * qty
        commission = cost * self._commission_pct
        total_cost = cost + commission
        if total_cost > self._cash:
            raise BrokerError(
                f"Insufficient cash: need {total_cost:.2f}, have {self._cash:.2f}"
            )
        self._cash -= total_cost

        if symbol in self._positions:
            pos = self._positions[symbol]
            total_qty = pos.qty + qty
            pos.avg_entry_price = (pos.avg_entry_price * pos.qty + price * qty) / total_qty
            pos.qty = total_qty
        else:
            self._positions[symbol] = Position(
                symbol=symbol,
                qty=qty,
                avg_entry_price=price,
                current_price=price,
                market_value=cost,
            )
        return self._record_fill(symbol, OrderSide.BUY, qty, price, commission)

    def _execute_sell(self, symbol: str, qty: float, price: float) -> FilledOrder:
        if symbol not in self._positions:
            raise BrokerError(f"No position to sell for {symbol}")
        pos = self._positions[symbol]
        if qty > pos.qty:
            raise BrokerError(f"Cannot sell {qty} shares, only have {pos.qty}")
        cost = price * qty
        commission = cost * self._commission_pct
        self._cash += cost - commission
        pos.qty -= qty
        if pos.qty <= 0:
            del self._positions[symbol]
        return self._record_fill(symbol, OrderSide.SELL, qty, price, commission)

    def _execute_sell_short(self, symbol: str, qty: float, price: float) -> FilledOrder:
        """Open (or add to) a short position. Proceeds are credited to cash; the
        liability lives in the SHORT position (subtracted from equity)."""
        if symbol in self._positions and self._positions[symbol].side == PositionSide.LONG:
            raise BrokerError(f"Cannot short {symbol}: holding a long (close it first)")
        proceeds = price * qty
        commission = proceeds * self._commission_pct
        self._cash += proceeds - commission
        if symbol in self._positions:
            pos = self._positions[symbol]
            total_qty = pos.qty + qty
            pos.avg_entry_price = (pos.avg_entry_price * pos.qty + price * qty) / total_qty
            pos.qty = total_qty
            pos.update_price(price)
        else:
            p = Position(
                symbol=symbol,
                qty=qty,
                side=PositionSide.SHORT,
                avg_entry_price=price,
                current_price=price,
            )
            p.update_price(price)
            self._positions[symbol] = p
        return self._record_fill(symbol, OrderSide.SELL_SHORT, qty, price, commission)

    def _execute_buy_to_cover(self, symbol: str, qty: float, price: float) -> FilledOrder:
        """Close (or reduce) a short position by buying back shares."""
        pos = self._positions.get(symbol)
        if pos is None or pos.side != PositionSide.SHORT:
            raise BrokerError(f"No short position to cover for {symbol}")
        if qty > pos.qty:
            raise BrokerError(f"Cannot cover {qty} shares, only short {pos.qty}")
        cost = price * qty
        commission = cost * self._commission_pct
        self._cash -= cost + commission
        pos.qty -= qty
        if pos.qty <= 0:
            del self._positions[symbol]
        else:
            pos.update_price(price)
        return self._record_fill(symbol, OrderSide.BUY_TO_COVER, qty, price, commission)

    def _record_fill(
        self, symbol: str, side: OrderSide, qty: float, price: float, commission: float
    ) -> FilledOrder:
        self._order_counter += 1
        filled = FilledOrder(
            order_id=f"sim_{self._order_counter}",
            symbol=symbol,
            side=side,
            qty=qty,
            filled_price=price,
            filled_at=datetime.now(),
            commission=commission,
        )
        self._fills[filled.order_id] = filled
        logger.debug(
            f"Simulated fill: {side.value} {qty} {symbol} "
            f"@ {price:.2f} (commission={commission:.2f})"
        )
        return filled

    def _pending(self, order_id: str, symbol: str, side: OrderSide) -> FilledOrder:
        """A not-yet-filled resting order: filled_price/qty 0, mirroring Alpaca."""
        return FilledOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            qty=0.0,
            filled_price=0.0,
            filled_at=datetime.now(),
        )

    def _remove_leg(self, leg: _RestingLeg) -> None:
        legs = self._resting.get(leg.symbol)
        if not legs:
            return
        self._resting[leg.symbol] = [l for l in legs if l.leg_id != leg.leg_id]
        if not self._resting[leg.symbol]:
            del self._resting[leg.symbol]

    def _cancel_group(self, leg: _RestingLeg) -> None:
        """Remove the leg and, if it belongs to an OCO group, its siblings."""
        if leg.group is None:
            self._remove_leg(leg)
            return
        legs = self._resting.get(leg.symbol)
        if not legs:
            return
        self._resting[leg.symbol] = [l for l in legs if l.group != leg.group]
        if not self._resting[leg.symbol]:
            del self._resting[leg.symbol]

    # ------------------------------------------------------------------ #
    # BaseBroker interface
    # ------------------------------------------------------------------ #
    def get_position(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    def get_all_positions(self) -> list[Position]:
        return list(self._positions.values())

    def get_open_orders(self, symbol: str | None = None) -> list[OpenOrder]:
        """Resting legs as OpenOrders (limit-> LIMIT, stop-> STOP)."""
        out: list[OpenOrder] = []
        for sym, legs in self._resting.items():
            if symbol is not None and sym != symbol.upper() and sym != symbol:
                continue
            for leg in legs:
                is_limit = leg.kind == "limit"
                out.append(OpenOrder(
                    order_id=leg.leg_id,
                    symbol=leg.symbol,
                    side=leg.side,
                    order_type=OrderType.LIMIT if is_limit else OrderType.STOP,
                    qty=leg.qty,
                    limit_price=leg.trigger_price if is_limit else None,
                    stop_price=None if is_limit else leg.trigger_price,
                ))
        return out

    def get_portfolio_state(self) -> PortfolioState:
        # A long adds its market value to equity; a short's proceeds are already
        # in cash, so its current market value is a LIABILITY (subtract it).
        equity = self._cash
        for p in self._positions.values():
            if p.side == PositionSide.SHORT:
                equity -= p.market_value
            else:
                equity += p.market_value
        return PortfolioState(
            cash=self._cash,
            equity=equity,
            positions=dict(self._positions),
        )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a resting order by leg id or OCO group id.

        Matching either handle cancels the whole OCO group (siblings included),
        like cancelling a bracket at a real broker. ``order_id`` may be the leg
        id returned for a resting entry or the group id returned for an OCO.
        """
        for legs in list(self._resting.values()):
            for leg in legs:
                if leg.leg_id == order_id or leg.group == order_id:
                    self._cancel_group(leg)
                    logger.debug(f"Cancelled resting order {order_id}")
                    return True
        return False

    def close_position(self, symbol: str) -> FilledOrder | None:
        pos = self._positions.get(symbol)
        if pos is None:
            return None
        # Closing a position invalidates any resting protection on it.
        self._resting.pop(symbol, None)
        # A long closes with SELL, a short with BUY_TO_COVER.
        close_side = (
            OrderSide.BUY_TO_COVER if pos.side == PositionSide.SHORT else OrderSide.SELL
        )
        order = Order(symbol=symbol, side=close_side, qty=pos.qty)
        return self.submit_order(order)

    def get_order_status(self, order_id: str) -> FilledOrder | None:
        return self._fills.get(order_id)

    def reset(self) -> None:
        """Reset broker to initial state."""
        self._cash = self._initial_capital
        self._positions.clear()
        self._order_counter = 0
        self._group_counter = 0
        self._current_prices.clear()
        self._resting.clear()
        self._fills.clear()

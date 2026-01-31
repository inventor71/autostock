from __future__ import annotations

import logging
from datetime import datetime

from src.core.models import FilledOrder, Order, Position, PortfolioState
from src.core.types import OrderSide
from src.core.exceptions import BrokerError
from src.execution.base import BaseBroker

logger = logging.getLogger(__name__)


class SimulatedBroker(BaseBroker):
    """Simulated broker for backtesting.

    Executes orders immediately at the specified price with optional commission.
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
        self._current_prices: dict[str, float] = {}

    def set_current_price(self, symbol: str, price: float) -> None:
        """Set current price for simulated fills."""
        self._current_prices[symbol] = price
        if symbol in self._positions:
            self._positions[symbol].update_price(price)

    def submit_order(self, order: Order) -> FilledOrder:
        price = self._current_prices.get(order.symbol)
        if price is None:
            raise BrokerError(f"No price set for {order.symbol}")

        cost = price * order.qty
        commission = cost * self._commission_pct

        if order.side == OrderSide.BUY:
            total_cost = cost + commission
            if total_cost > self._cash:
                raise BrokerError(
                    f"Insufficient cash: need {total_cost:.2f}, have {self._cash:.2f}"
                )
            self._cash -= total_cost

            if order.symbol in self._positions:
                pos = self._positions[order.symbol]
                total_qty = pos.qty + order.qty
                pos.avg_entry_price = (
                    (pos.avg_entry_price * pos.qty + price * order.qty) / total_qty
                )
                pos.qty = total_qty
            else:
                self._positions[order.symbol] = Position(
                    symbol=order.symbol,
                    qty=order.qty,
                    avg_entry_price=price,
                    current_price=price,
                    market_value=cost,
                )
        else:  # SELL
            if order.symbol not in self._positions:
                raise BrokerError(f"No position to sell for {order.symbol}")
            pos = self._positions[order.symbol]
            if order.qty > pos.qty:
                raise BrokerError(
                    f"Cannot sell {order.qty} shares, only have {pos.qty}"
                )
            self._cash += cost - commission
            pos.qty -= order.qty
            if pos.qty <= 0:
                del self._positions[order.symbol]

        self._order_counter += 1
        filled = FilledOrder(
            order_id=f"sim_{self._order_counter}",
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            filled_price=price,
            filled_at=datetime.now(),
            commission=commission,
        )

        logger.debug(
            f"Simulated fill: {order.side.value} {order.qty} {order.symbol} "
            f"@ {price:.2f} (commission={commission:.2f})"
        )
        return filled

    def get_position(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    def get_all_positions(self) -> list[Position]:
        return list(self._positions.values())

    def get_portfolio_state(self) -> PortfolioState:
        equity = self._cash + sum(p.market_value for p in self._positions.values())
        return PortfolioState(
            cash=self._cash,
            equity=equity,
            positions=dict(self._positions),
        )

    def cancel_order(self, order_id: str) -> bool:
        return True  # No pending orders in simulation

    def close_position(self, symbol: str) -> FilledOrder | None:
        pos = self._positions.get(symbol)
        if pos is None:
            return None
        order = Order(symbol=symbol, side=OrderSide.SELL, qty=pos.qty)
        return self.submit_order(order)

    def reset(self) -> None:
        """Reset broker to initial state."""
        self._cash = self._initial_capital
        self._positions.clear()
        self._order_counter = 0
        self._current_prices.clear()

from __future__ import annotations

import time
from datetime import datetime

from loguru import logger

from src.core.exceptions import BrokerError
from src.core.models import FilledOrder, OpenOrder, Order, Position, PortfolioState
from src.core.types import OrderClass, OrderSide, OrderType
from src.execution.base import BaseBroker

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import (
        MarketOrderRequest,
        LimitOrderRequest,
        StopOrderRequest,
        StopLimitOrderRequest,
        TakeProfitRequest,
        StopLossRequest,
        GetOrdersRequest,
    )
    from alpaca.trading.enums import (
        OrderSide as AlpacaSide,
        OrderClass as AlpacaOrderClass,
        OrderStatus,
        QueryOrderStatus,
        TimeInForce,
    )
except ImportError:
    TradingClient = None


_ALPACA_TO_ORDER_TYPE = {
    "market": OrderType.MARKET,
    "limit": OrderType.LIMIT,
    "stop": OrderType.STOP,
    "stop_limit": OrderType.STOP_LIMIT,
}

_TERMINAL_STATUSES = frozenset(
    {
        "filled",
        "canceled",
        "expired",
        "rejected",
        "done_for_day",
        "replaced",
        "stopped",
        "suspended",
    }
)


class AlpacaBroker(BaseBroker):
    """Broker implementation using Alpaca Trading API."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        paper: bool = True,
        fill_poll_timeout: float = 5.0,
        fill_poll_interval: float = 0.2,
    ):
        if TradingClient is None:
            raise BrokerError("alpaca-py not installed")
        self._client = TradingClient(api_key, secret_key, paper=paper)
        self._paper = paper
        self._fill_poll_timeout = fill_poll_timeout
        self._fill_poll_interval = fill_poll_interval
        logger.info(f"AlpacaBroker initialized (paper={paper})")

    def _poll_for_fill(self, order_id: str):
        """Poll an order until terminal status or timeout; return latest order object."""
        deadline = time.monotonic() + self._fill_poll_timeout
        latest = self._client.get_order_by_id(order_id)
        while time.monotonic() < deadline:
            status = str(latest.status).split(".")[-1].lower()
            if status in _TERMINAL_STATUSES:
                return latest
            time.sleep(self._fill_poll_interval)
            latest = self._client.get_order_by_id(order_id)
        return latest

    def submit_order(self, order: Order) -> FilledOrder:
        try:
            side = AlpacaSide.BUY if order.side == OrderSide.BUY else AlpacaSide.SELL
            request = self._build_request(order, side)

            result = self._client.submit_order(request)
            logger.info(
                f"Order submitted: {order.side.value} {order.qty} {order.symbol} "
                f"(id={result.id})"
            )

            settled = self._poll_for_fill(str(result.id))
            filled_price = float(settled.filled_avg_price or 0)
            filled_qty = float(settled.filled_qty or 0) or order.qty
            status = str(settled.status).split(".")[-1].lower()
            if filled_price == 0:
                logger.warning(
                    f"Order {result.id} not filled within "
                    f"{self._fill_poll_timeout}s (status={status}); "
                    f"call get_order_status() later to refresh"
                )

            return FilledOrder(
                order_id=str(settled.id),
                symbol=order.symbol,
                side=order.side,
                qty=filled_qty,
                filled_price=filled_price,
                filled_at=settled.filled_at or datetime.now(),
            )

        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(f"Order submission failed: {e}") from e

    def _time_in_force(self, order: Order):
        """Protective legs persist across sessions (GTC); simple orders honour
        the order's TIF (default DAY)."""
        if order.order_class in (OrderClass.BRACKET, OrderClass.OCO):
            return TimeInForce.GTC
        return TimeInForce.GTC if str(order.time_in_force).lower() == "gtc" else TimeInForce.DAY

    def _build_request(self, order: Order, side):
        """Map an Order to the matching Alpaca request, including bracket/OCO."""
        tif = self._time_in_force(order)

        if order.order_class == OrderClass.BRACKET:
            # Entry leg + OCO protection: LIMIT take-profit, plain STOP stop-loss
            # (stop_price only -> market-on-touch, guaranteed exit).
            take_profit = TakeProfitRequest(limit_price=order.take_profit_price)
            stop_loss = StopLossRequest(stop_price=order.stop_loss_price)
            kwargs = dict(
                symbol=order.symbol,
                qty=order.qty,
                side=side,
                time_in_force=tif,
                order_class=AlpacaOrderClass.BRACKET,
                take_profit=take_profit,
                stop_loss=stop_loss,
            )
            if order.order_type == OrderType.LIMIT:
                return LimitOrderRequest(limit_price=order.limit_price, **kwargs)
            return MarketOrderRequest(**kwargs)

        if order.order_class == OrderClass.OCO:
            # Protection over an existing position: take-profit rides on
            # limit_price, stop-loss is a plain STOP leg.
            stop_loss = StopLossRequest(stop_price=order.stop_loss_price)
            return LimitOrderRequest(
                symbol=order.symbol,
                qty=order.qty,
                side=side,
                time_in_force=tif,
                limit_price=order.take_profit_price,
                order_class=AlpacaOrderClass.OCO,
                stop_loss=stop_loss,
            )

        if order.order_type == OrderType.MARKET:
            return MarketOrderRequest(
                symbol=order.symbol, qty=order.qty, side=side, time_in_force=tif
            )
        if order.order_type == OrderType.LIMIT:
            return LimitOrderRequest(
                symbol=order.symbol, qty=order.qty, side=side, time_in_force=tif,
                limit_price=order.limit_price,
            )
        if order.order_type == OrderType.STOP:
            return StopOrderRequest(
                symbol=order.symbol, qty=order.qty, side=side, time_in_force=tif,
                stop_price=order.stop_price,
            )
        if order.order_type == OrderType.STOP_LIMIT:
            return StopLimitOrderRequest(
                symbol=order.symbol, qty=order.qty, side=side, time_in_force=tif,
                limit_price=order.limit_price, stop_price=order.stop_price,
            )
        raise BrokerError(f"Unsupported order type: {order.order_type}")

    def get_position(self, symbol: str) -> Position | None:
        try:
            pos = self._client.get_open_position(symbol)
            return Position(
                symbol=pos.symbol,
                qty=float(pos.qty),
                avg_entry_price=float(pos.avg_entry_price),
                current_price=float(pos.current_price),
                unrealized_pnl=float(pos.unrealized_pl),
                market_value=float(pos.market_value),
            )
        except Exception:
            return None

    def get_open_orders(self, symbol: str | None = None) -> list[OpenOrder]:
        """Open orders at Alpaca (e.g. resting bracket protective legs)."""
        try:
            req = GetOrdersRequest(
                status=QueryOrderStatus.OPEN,
                symbols=[symbol] if symbol else None,
            )
            orders = self._client.get_orders(filter=req)
        except Exception as e:
            logger.warning(f"Failed to fetch open orders: {e}")
            return []

        out: list[OpenOrder] = []
        for o in orders:
            side = OrderSide.BUY if str(o.side).split(".")[-1].lower() == "buy" else OrderSide.SELL
            otype = _ALPACA_TO_ORDER_TYPE.get(
                str(o.order_type).split(".")[-1].lower(), OrderType.MARKET
            )
            out.append(OpenOrder(
                order_id=str(o.id),
                symbol=o.symbol,
                side=side,
                order_type=otype,
                qty=float(o.qty or 0),
                limit_price=float(o.limit_price) if o.limit_price else None,
                stop_price=float(o.stop_price) if o.stop_price else None,
            ))
        return out

    def get_all_positions(self) -> list[Position]:
        try:
            positions = self._client.get_all_positions()
            return [
                Position(
                    symbol=p.symbol,
                    qty=float(p.qty),
                    avg_entry_price=float(p.avg_entry_price),
                    current_price=float(p.current_price),
                    unrealized_pnl=float(p.unrealized_pl),
                    market_value=float(p.market_value),
                )
                for p in positions
            ]
        except Exception as e:
            raise BrokerError(f"Failed to get positions: {e}") from e

    def get_portfolio_state(self) -> PortfolioState:
        try:
            account = self._client.get_account()
            positions = self.get_all_positions()
            return PortfolioState(
                cash=float(account.cash),
                equity=float(account.equity),
                positions={p.symbol: p for p in positions},
            )
        except Exception as e:
            raise BrokerError(f"Failed to get portfolio state: {e}") from e

    def cancel_order(self, order_id: str) -> bool:
        try:
            self._client.cancel_order_by_id(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to cancel order {order_id}: {e}")
            return False

    def close_position(self, symbol: str) -> FilledOrder | None:
        try:
            result = self._client.close_position(symbol)
            logger.info(f"Position closed: {symbol}")

            settled = self._poll_for_fill(str(result.id))
            filled_price = float(settled.filled_avg_price or 0)
            filled_qty = float(settled.filled_qty or 0) or float(result.qty or 0)
            status = str(settled.status).split(".")[-1].lower()
            if filled_price == 0:
                logger.warning(
                    f"Close order {result.id} for {symbol} not filled within "
                    f"{self._fill_poll_timeout}s (status={status})"
                )

            return FilledOrder(
                order_id=str(settled.id),
                symbol=symbol,
                side=OrderSide.SELL,
                qty=filled_qty,
                filled_price=filled_price,
                filled_at=settled.filled_at or datetime.now(),
            )
        except Exception as e:
            logger.warning(f"Failed to close position {symbol}: {e}")
            return None

    def get_order_status(self, order_id: str) -> FilledOrder | None:
        try:
            o = self._client.get_order_by_id(order_id)
        except Exception as e:
            logger.warning(f"Failed to fetch order {order_id}: {e}")
            return None
        side = OrderSide.BUY if str(o.side).split(".")[-1].lower() == "buy" else OrderSide.SELL
        return FilledOrder(
            order_id=str(o.id),
            symbol=o.symbol,
            side=side,
            qty=float(o.filled_qty or o.qty or 0),
            filled_price=float(o.filled_avg_price or 0),
            filled_at=o.filled_at or datetime.now(),
        )

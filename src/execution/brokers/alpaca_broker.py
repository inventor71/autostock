from __future__ import annotations

from datetime import datetime

from loguru import logger

from src.core.exceptions import BrokerError
from src.core.models import FilledOrder, Order, Position, PortfolioState
from src.core.types import OrderSide, OrderType
from src.execution.base import BaseBroker

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import (
        MarketOrderRequest,
        LimitOrderRequest,
        StopOrderRequest,
        StopLimitOrderRequest,
    )
    from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce
except ImportError:
    TradingClient = None


class AlpacaBroker(BaseBroker):
    """Broker implementation using Alpaca Trading API."""

    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        if TradingClient is None:
            raise BrokerError("alpaca-py not installed")
        self._client = TradingClient(api_key, secret_key, paper=paper)
        self._paper = paper
        logger.info(f"AlpacaBroker initialized (paper={paper})")

    def submit_order(self, order: Order) -> FilledOrder:
        try:
            side = AlpacaSide.BUY if order.side == OrderSide.BUY else AlpacaSide.SELL
            tif = TimeInForce.DAY

            if order.order_type == OrderType.MARKET:
                request = MarketOrderRequest(
                    symbol=order.symbol,
                    qty=order.qty,
                    side=side,
                    time_in_force=tif,
                )
            elif order.order_type == OrderType.LIMIT:
                request = LimitOrderRequest(
                    symbol=order.symbol,
                    qty=order.qty,
                    side=side,
                    time_in_force=tif,
                    limit_price=order.limit_price,
                )
            elif order.order_type == OrderType.STOP:
                request = StopOrderRequest(
                    symbol=order.symbol,
                    qty=order.qty,
                    side=side,
                    time_in_force=tif,
                    stop_price=order.stop_price,
                )
            elif order.order_type == OrderType.STOP_LIMIT:
                request = StopLimitOrderRequest(
                    symbol=order.symbol,
                    qty=order.qty,
                    side=side,
                    time_in_force=tif,
                    limit_price=order.limit_price,
                    stop_price=order.stop_price,
                )
            else:
                raise BrokerError(f"Unsupported order type: {order.order_type}")

            result = self._client.submit_order(request)
            logger.info(
                f"Order submitted: {order.side.value} {order.qty} {order.symbol} "
                f"(id={result.id})"
            )

            return FilledOrder(
                order_id=str(result.id),
                symbol=order.symbol,
                side=order.side,
                qty=order.qty,
                filled_price=float(result.filled_avg_price or 0),
                filled_at=result.filled_at or datetime.now(),
            )

        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(f"Order submission failed: {e}") from e

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
            return FilledOrder(
                order_id=str(result.id),
                symbol=symbol,
                side=OrderSide.SELL,
                qty=float(result.qty or 0),
                filled_price=float(result.filled_avg_price or 0),
                filled_at=result.filled_at or datetime.now(),
            )
        except Exception as e:
            logger.warning(f"Failed to close position {symbol}: {e}")
            return None

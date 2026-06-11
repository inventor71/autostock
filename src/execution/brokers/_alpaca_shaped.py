"""Shared base for the two Alpaca-shaped brokers (R3 dedup).

``AlpacaBroker`` (Alpaca Trading API) and ``AccountFarmBroker`` (Alpaca Broker API,
sandbox account farm) were ~80% duplicated — same request-building, fill polling,
position/order mapping, market clock, shortable check, and latest-prices logic over
two different SDK client surfaces. This base owns that shared algorithm as a
template-method class; each subclass supplies only the thin client-specific hooks
(``_do_*``) and its SDK request-class set.

Behaviour-preserving (R3 is T1): the three real behavioural divergences are routed
through overridable members so each subclass keeps its exact current behaviour —
- ``_alpaca_side``  : base = correct mapping (Alpaca); AccountFarmBroker overrides
  with its current simpler mapping (the BUY_TO_COVER→SELL quirk is preserved; the
  fix is deferred to track R7).
- ``_time_in_force``: base = F9 fail-closed map (Alpaca); AccountFarmBroker overrides
  with its gtc→GTC else→DAY downgrade (preserved; fix deferred to R7).
- ``_extras``       : base = ``{}`` (AccountFarmBroker); AlpacaBroker overrides to pass
  extended_hours / client_order_id. Trailing-stop support is gated on ``_req_trailing``.
"""
from __future__ import annotations

from abc import abstractmethod
from datetime import datetime

from loguru import logger

from src.core.exceptions import BrokerError
from src.core.models import FilledOrder, OpenOrder, Order, Position, PortfolioState
from src.core.types import OrderClass, OrderSide, OrderType, PositionSide
from src.execution.base import BaseBroker

try:
    # Order-protection legs + the orders query + enums all come from the Trading
    # namespace for BOTH brokers (the Broker API reuses them), so the base can own
    # them directly. Only the order *envelope* classes differ per SDK — those are
    # supplied by each subclass as instance attrs in __init__.
    from alpaca.trading.requests import (
        TakeProfitRequest,
        StopLossRequest,
        GetOrdersRequest,
    )
    from alpaca.trading.enums import (
        OrderSide as AlpacaSide,
        OrderClass as AlpacaOrderClass,
        TimeInForce,
    )
except ImportError:  # pragma: no cover - guarded by each subclass __init__
    TakeProfitRequest = StopLossRequest = GetOrdersRequest = None
    AlpacaSide = AlpacaOrderClass = TimeInForce = None


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


class AlpacaShapedBroker(BaseBroker):
    """Template-method base for Alpaca Trading-API and Broker-API brokers.

    Subclasses MUST set, in ``__init__`` (after the alpaca-py guard):
      - ``_fill_poll_timeout`` / ``_fill_poll_interval``
      - request envelope classes ``_req_market/_req_limit/_req_stop/_req_stop_limit``
        and ``_req_trailing`` (None if unsupported)
      - ``_open_orders_status`` (a ``QueryOrderStatus``)
    and implement the ``_do_*`` client hooks + ``_make_data_client`` + ``get_fills``.
    """

    # Default: don't client-side filter terminal orders (Alpaca's OPEN query already
    # excludes them). AccountFarmBroker sets True (its ALL query needs the filter).
    _open_orders_skip_terminal: bool = False

    # SDK request-envelope classes — set per-subclass in __init__ (after the
    # alpaca-py guard). Plain class-attr defaults so an instance attr overrides them
    # cleanly (no descriptor). ``_req_trailing`` stays None where unsupported.
    _req_market = None
    _req_limit = None
    _req_stop = None
    _req_stop_limit = None
    _req_trailing = None
    _open_orders_status = None

    # ── behavioural hooks (overridable; see module docstring / R3 ledger) ──

    @staticmethod
    def _alpaca_side(side: OrderSide):
        """Map our OrderSide → Alpaca's BUY/SELL. Default = the correct full mapping
        (Alpaca has no explicit short sides: a SELL on a flat symbol opens a short,
        a BUY covers). AccountFarmBroker overrides to preserve its current behaviour."""
        if side in (OrderSide.BUY, OrderSide.BUY_TO_COVER):
            return AlpacaSide.BUY
        if side in (OrderSide.SELL, OrderSide.SELL_SHORT):
            return AlpacaSide.SELL
        raise BrokerError(f"unsupported order side: {side!r}")

    _TIF_MAP = {"day": "DAY", "gtc": "GTC", "ioc": "IOC", "fok": "FOK"}

    @classmethod
    def _tif_value(cls, tif_str: str):
        key = str(tif_str).lower()
        try:
            return getattr(TimeInForce, cls._TIF_MAP[key])
        except KeyError:
            raise BrokerError(
                f"unsupported time_in_force: {tif_str!r} "
                f"(supported: day/gtc/ioc/fok; opg/cls not wired in F9 v1)"
            )

    def _time_in_force(self, order: Order):
        """Protective legs persist across sessions (GTC); simple orders honour the
        order's TIF, fail-closed on unsupported (F9). AccountFarmBroker overrides."""
        if order.order_class in (OrderClass.BRACKET, OrderClass.OCO):
            return TimeInForce.GTC
        return self._tif_value(order.time_in_force)

    def _extras(self, order: Order) -> dict:
        """extended_hours / client_order_id passthrough for simple-class orders.
        Default = none (AccountFarmBroker); AlpacaBroker overrides."""
        return {}

    # ── shared static mappers ──

    @staticmethod
    def _position_side(pos) -> PositionSide:
        """Map Alpaca's position side ('long'/'short') to ours; a short reports a
        negative qty which we normalize to positive (direction lives in side, F54)."""
        raw = str(getattr(pos, "side", "")).split(".")[-1].lower()
        if raw == "short":
            return PositionSide.SHORT
        try:
            if float(pos.qty) < 0:
                return PositionSide.SHORT
        except (TypeError, ValueError):
            pass
        return PositionSide.LONG

    @staticmethod
    def _to_open_order(o, default_symbol: str | None = None) -> OpenOrder:
        side = (
            OrderSide.BUY
            if str(o.side).split(".")[-1].lower() == "buy"
            else OrderSide.SELL
        )
        otype = _ALPACA_TO_ORDER_TYPE.get(
            str(o.order_type).split(".")[-1].lower(), OrderType.MARKET
        )
        return OpenOrder(
            order_id=str(o.id),
            symbol=o.symbol or default_symbol,
            side=side,
            order_type=otype,
            qty=float(o.qty or 0),
            limit_price=float(o.limit_price) if o.limit_price else None,
            stop_price=float(o.stop_price) if o.stop_price else None,
        )

    # ── client hooks (subclass one-liners over its SDK client) ──

    @abstractmethod
    def _do_submit(self, request): ...
    @abstractmethod
    def _do_get_order(self, order_id: str): ...
    @abstractmethod
    def _do_cancel(self, order_id: str) -> None: ...
    @abstractmethod
    def _do_close(self, symbol: str): ...
    @abstractmethod
    def _do_get_open_position(self, symbol: str): ...
    @abstractmethod
    def _do_get_all_positions(self) -> list: ...
    @abstractmethod
    def _do_get_account(self): ...
    @abstractmethod
    def _do_get_orders(self, filter): ...
    @abstractmethod
    def _do_get_clock(self): ...
    @abstractmethod
    def _do_get_asset(self, symbol: str): ...
    @abstractmethod
    def _make_data_client(self): ...

    # ── request building ──

    def _build_request(self, order: Order, side):
        """Map an Order to the matching Alpaca request, including bracket/OCO.

        Uses the subclass-provided envelope classes (``_req_*``). The protection
        legs come from the Trading namespace (shared). ``_extras`` and trailing-stop
        availability are subclass-controlled (preserved divergences D3)."""
        tif = self._time_in_force(order)

        if order.order_class == OrderClass.BRACKET:
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
                return self._req_limit(limit_price=order.limit_price, **kwargs)
            return self._req_market(**kwargs)

        if order.order_class == OrderClass.OCO:
            take_profit = TakeProfitRequest(limit_price=order.take_profit_price)
            stop_loss = StopLossRequest(stop_price=order.stop_loss_price)
            return self._req_limit(
                symbol=order.symbol,
                qty=order.qty,
                side=side,
                time_in_force=tif,
                limit_price=order.take_profit_price,
                order_class=AlpacaOrderClass.OCO,
                take_profit=take_profit,
                stop_loss=stop_loss,
            )

        base = dict(
            symbol=order.symbol, qty=order.qty, side=side, time_in_force=tif,
            **self._extras(order),
        )
        if order.order_type == OrderType.MARKET:
            return self._req_market(**base)
        if order.order_type == OrderType.LIMIT:
            return self._req_limit(limit_price=order.limit_price, **base)
        if order.order_type == OrderType.STOP:
            return self._req_stop(stop_price=order.stop_price, **base)
        if order.order_type == OrderType.STOP_LIMIT:
            return self._req_stop_limit(
                limit_price=order.limit_price, stop_price=order.stop_price, **base
            )
        if order.order_type == OrderType.TRAILING_STOP and self._req_trailing is not None:
            trail = (
                {"trail_price": order.trail_price}
                if order.trail_price is not None
                else {"trail_percent": order.trail_percent}
            )
            return self._req_trailing(**trail, **base)
        raise BrokerError(f"Unsupported order type: {order.order_type}")

    # ── order lifecycle ──

    def _poll_for_fill(self, order_id: str):
        """Poll an order until terminal status or timeout; return latest order."""
        import time

        deadline = time.monotonic() + self._fill_poll_timeout
        latest = self._do_get_order(order_id)
        while time.monotonic() < deadline:
            status = str(latest.status).split(".")[-1].lower()
            if status in _TERMINAL_STATUSES:
                return latest
            time.sleep(self._fill_poll_interval)
            latest = self._do_get_order(order_id)
        return latest

    def submit_order(self, order: Order) -> FilledOrder:
        try:
            side = self._alpaca_side(order.side)
            request = self._build_request(order, side)

            result = self._do_submit(request)
            logger.info(
                f"Order submitted: {order.side.value} {order.qty} {order.symbol} "
                f"(id={result.id})"
            )

            settled = self._poll_for_fill(str(result.id))
            filled_price = float(getattr(settled, "filled_avg_price", None) or 0)
            filled_qty = float(getattr(settled, "filled_qty", None) or 0) or order.qty
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
                filled_at=getattr(settled, "filled_at", None) or datetime.now(),
            )

        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(f"Order submission failed: {e}") from e

    def get_order_status(self, order_id: str) -> FilledOrder | None:
        try:
            o = self._do_get_order(order_id)
        except Exception as e:
            logger.warning(f"Failed to fetch order {order_id}: {e}")
            return None
        side = (
            OrderSide.BUY
            if str(o.side).split(".")[-1].lower() == "buy"
            else OrderSide.SELL
        )
        return FilledOrder(
            order_id=str(o.id),
            symbol=o.symbol,
            side=side,
            qty=float(getattr(o, "filled_qty", None) or getattr(o, "qty", None) or 0),
            filled_price=float(getattr(o, "filled_avg_price", None) or 0),
            filled_at=getattr(o, "filled_at", None) or datetime.now(),
        )

    def cancel_order(self, order_id: str) -> bool:
        try:
            self._do_cancel(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to cancel order {order_id}: {e}")
            return False

    def close_position(self, symbol: str) -> FilledOrder | None:
        try:
            result = self._do_close(symbol)
            logger.info(f"Position closed: {symbol}")

            settled = self._poll_for_fill(str(result.id))
            filled_price = float(getattr(settled, "filled_avg_price", None) or 0)
            filled_qty = float(
                getattr(settled, "filled_qty", None) or 0
            ) or float(getattr(result, "qty", None) or 0)
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
                filled_at=getattr(settled, "filled_at", None) or datetime.now(),
            )
        except Exception as e:
            logger.warning(f"Failed to close position {symbol}: {e}")
            return None

    # ── positions / account ──

    def get_position(self, symbol: str) -> Position | None:
        try:
            pos = self._do_get_open_position(symbol)
            return Position(
                symbol=pos.symbol,
                qty=abs(float(pos.qty)),
                side=self._position_side(pos),
                avg_entry_price=float(pos.avg_entry_price),
                current_price=float(pos.current_price),
                unrealized_pnl=float(pos.unrealized_pl),
                market_value=abs(float(pos.market_value)),
            )
        except Exception:
            return None

    def get_all_positions(self) -> list[Position]:
        try:
            positions = self._do_get_all_positions()
            return [
                Position(
                    symbol=p.symbol,
                    qty=abs(float(p.qty)),
                    side=self._position_side(p),
                    avg_entry_price=float(p.avg_entry_price),
                    current_price=float(p.current_price),
                    unrealized_pnl=float(p.unrealized_pl),
                    market_value=abs(float(p.market_value)),
                )
                for p in positions
            ]
        except Exception as e:
            raise BrokerError(f"Failed to get positions: {e}") from e

    def get_portfolio_state(self) -> PortfolioState:
        try:
            account = self._do_get_account()
            positions = self.get_all_positions()
            return PortfolioState(
                cash=float(account.cash),
                equity=float(account.equity),
                positions={p.symbol: p for p in positions},
            )
        except Exception as e:
            raise BrokerError(f"Failed to get portfolio state: {e}") from e

    # ── market clock / shortable ──

    def is_market_open(self, retries: int = 3, delay: float = 1.0) -> bool:
        """True only during the regular session. Retries on transient errors and
        fails closed (False) only if every attempt fails."""
        import time

        last_err = None
        for attempt in range(retries):
            try:
                return bool(self._do_get_clock().is_open)
            except Exception as e:
                last_err = e
                if attempt < retries - 1:
                    time.sleep(delay)
        logger.warning(f"Could not fetch market clock after {retries} tries: {last_err}")
        return False

    def is_shortable(self, symbol: str) -> bool:
        """F60: True only if tradable AND shortable AND easy_to_borrow. Fail-closed;
        confirmed determinations cached for ``_etb_ttl``; transient failures are NOT
        cached (would block the symbol for the whole TTL after recovery)."""
        import time

        sym = symbol.upper()
        now = time.monotonic()
        hit = self._etb_cache.get(sym)
        if hit is not None and (now - hit[1]) < self._etb_ttl:
            return hit[0]
        try:
            asset = self._do_get_asset(sym)
        except Exception as e:
            logger.warning(f"is_shortable({sym}) check failed; treating as NOT shortable: {e}")
            return False
        ok = bool(
            getattr(asset, "tradable", False)
            and getattr(asset, "shortable", False)
            and getattr(asset, "easy_to_borrow", False)
        )
        self._etb_cache[sym] = (ok, now)
        return ok

    # ── open orders ──

    def get_open_orders(self, symbol: str | None = None) -> list[OpenOrder]:
        """Open orders incl. bracket/OCO protective legs. Uses ``nested=True`` and
        flattens each order's ``legs`` (dedup by id) so the stop-loss leg is surfaced.
        Subclasses pick the status filter (``_open_orders_status``) and whether to
        client-side skip terminal orders (``_open_orders_skip_terminal``)."""
        try:
            req = GetOrdersRequest(
                status=self._open_orders_status,
                symbols=[symbol] if symbol else None,
                nested=True,
            )
            orders = self._do_get_orders(req)
        except Exception as e:
            logger.warning(f"Failed to fetch open orders: {e}")
            return []

        out: list[OpenOrder] = []
        seen: set[str] = set()
        for o in orders:
            for node in [o, *(getattr(o, "legs", None) or [])]:
                sid = str(node.id)
                if sid in seen:
                    continue
                if self._open_orders_skip_terminal:
                    status = str(getattr(node, "status", "")).split(".")[-1].lower()
                    if status in _TERMINAL_STATUSES:
                        continue
                seen.add(sid)
                out.append(self._to_open_order(node, default_symbol=o.symbol))
        return out

    # ── market data ──

    def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        """Latest trade price per symbol (read-only, best-effort). The data-client
        construction differs per SDK and is supplied by ``_make_data_client``.
        Failure → {} (never kills the caller, NFR-4)."""
        syms = [s for s in dict.fromkeys(symbols) if s]
        if not syms:
            return {}
        try:
            if self._data_client is None:
                self._data_client = self._make_data_client()
            from alpaca.data.requests import StockLatestTradeRequest

            trades = self._data_client.get_stock_latest_trade(
                StockLatestTradeRequest(symbol_or_symbols=syms)
            )
            return {sym: float(tr.price) for sym, tr in trades.items()}
        except Exception as e:
            logger.warning(f"get_latest_prices failed: {e}")
            return {}

    # ── subclass-specific (kept in subclasses): get_fills, record_trade_ledger,
    #    __init__, the SDK request-class attrs, and any native overrides. ──

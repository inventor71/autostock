from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from src.agent.intraday.records import FillEvent
from src.agent.trades_log import record_trades
from src.core.exceptions import BrokerError
from src.core.models import FilledOrder, OpenOrder, Order, Position, PortfolioState
from src.core.types import OrderClass, OrderSide, OrderType, PositionSide
from src.execution.base import BaseBroker
from src.execution.brokers.session_timeout import install_session_timeout

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import (
        MarketOrderRequest,
        LimitOrderRequest,
        StopOrderRequest,
        StopLimitOrderRequest,
        TrailingStopOrderRequest,
        ReplaceOrderRequest,
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
        http_connect_timeout: float = 3.0,
        http_read_timeout: float = 5.0,
    ):
        if TradingClient is None:
            raise BrokerError("alpaca-py not installed")
        self._client = TradingClient(api_key, secret_key, paper=paper)
        # F14: bound every HTTP call so a half-open socket can't wedge the daemon.
        self._http_connect_timeout = http_connect_timeout
        self._http_read_timeout = http_read_timeout
        install_session_timeout(
            self._client, connect=http_connect_timeout, read=http_read_timeout
        )
        self._paper = paper
        self._fill_poll_timeout = fill_poll_timeout
        self._fill_poll_interval = fill_poll_interval
        # F8: keep keys to lazily build a market-data client for get_latest_prices
        # (current price of resting-order symbols we don't hold). Built on first use.
        self._api_key = api_key
        self._secret_key = secret_key
        self._data_client = None
        # F60: easy-to-borrow cache. ETB status changes ~daily, so a short TTL
        # avoids a get_asset call on every short check without going stale.
        self._etb_cache: dict[str, tuple[bool, float]] = {}
        self._etb_ttl = 1800.0  # 30 min
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

    # F54: map our OrderSide → Alpaca's side. Alpaca's OrderSide is only BUY/SELL;
    # it has no explicit short sides — a plain SELL on a flat symbol opens a short
    # and a plain BUY covers it (direction is account-state driven). So our
    # explicit SELL_SHORT collapses to Alpaca SELL and BUY_TO_COVER to Alpaca BUY.
    # We keep the distinction in OUR domain (Decision/Order/Position.side) for
    # unambiguous intent + audit, and only flatten it at this boundary.
    @staticmethod
    def _alpaca_side(side: OrderSide):
        if side in (OrderSide.BUY, OrderSide.BUY_TO_COVER):
            return AlpacaSide.BUY
        if side in (OrderSide.SELL, OrderSide.SELL_SHORT):
            return AlpacaSide.SELL
        raise BrokerError(f"unsupported order side: {side!r}")

    def submit_order(self, order: Order) -> FilledOrder:
        try:
            side = self._alpaca_side(order.side)
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

    # F9: supported TIFs are wired explicitly; anything else is rejected (no
    # silent downgrade to DAY — that was a latent fail-closed violation).
    _TIF_MAP = {
        "day": "DAY",
        "gtc": "GTC",
        "ioc": "IOC",
        "fok": "FOK",
    }

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
        """Protective legs persist across sessions (GTC); simple orders honour
        the order's TIF. Unsupported TIFs raise (fail-closed) instead of being
        silently downgraded to DAY (F9 fix)."""
        if order.order_class in (OrderClass.BRACKET, OrderClass.OCO):
            return TimeInForce.GTC
        return self._tif_value(order.time_in_force)

    def _extras(self, order: Order) -> dict:
        """extended_hours / client_order_id passthrough for simple-class orders."""
        kw: dict = {}
        if order.extended_hours:
            kw["extended_hours"] = True
        if order.client_order_id:
            kw["client_order_id"] = order.client_order_id
        return kw

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
            # Protection over an existing position: a take-profit LIMIT leg + a
            # stop-loss STOP leg. Alpaca requires an explicit take_profit leg
            # (not just the base limit_price).
            #
            # NOTE: extended_hours is intentionally NOT set here (it would be
            # rejected). Alpaca only allows extended_hours on DAY+LIMIT orders;
            # this OCO is GTC and carries a STOP leg, so enabling it fails the
            # order outright and removes protection. Coverage works by the GTC
            # STOP liquidating overnight/extended-hours gaps as market-on-touch
            # at the next regular-session open (opening auction) -- not during
            # the extended session itself. Intra-extended-hours exit would need
            # a separate DAY+LIMIT order, which a STOP cannot provide.
            take_profit = TakeProfitRequest(limit_price=order.take_profit_price)
            stop_loss = StopLossRequest(stop_price=order.stop_loss_price)
            return LimitOrderRequest(
                symbol=order.symbol,
                qty=order.qty,
                side=side,
                time_in_force=tif,
                limit_price=order.take_profit_price,
                order_class=AlpacaOrderClass.OCO,
                take_profit=take_profit,
                stop_loss=stop_loss,
            )

        base = dict(symbol=order.symbol, qty=order.qty, side=side, time_in_force=tif,
                    **self._extras(order))
        if order.order_type == OrderType.MARKET:
            return MarketOrderRequest(**base)
        if order.order_type == OrderType.LIMIT:
            return LimitOrderRequest(limit_price=order.limit_price, **base)
        if order.order_type == OrderType.STOP:
            return StopOrderRequest(stop_price=order.stop_price, **base)
        if order.order_type == OrderType.STOP_LIMIT:
            return StopLimitOrderRequest(
                limit_price=order.limit_price, stop_price=order.stop_price, **base
            )
        if order.order_type == OrderType.TRAILING_STOP:
            trail = (
                {"trail_price": order.trail_price}
                if order.trail_price is not None
                else {"trail_percent": order.trail_percent}
            )
            return TrailingStopOrderRequest(**trail, **base)
        raise BrokerError(f"Unsupported order type: {order.order_type}")

    @staticmethod
    def _position_side(pos) -> PositionSide:
        """Map Alpaca's position ``side`` ('long'/'short') to ours. Alpaca reports
        a short position's ``qty`` as negative; we normalize qty to positive and
        carry direction in ``side`` (F54 convention)."""
        raw = str(getattr(pos, "side", "")).split(".")[-1].lower()
        if raw == "short":
            return PositionSide.SHORT
        # Fallback: a negative qty also indicates a short.
        try:
            if float(pos.qty) < 0:
                return PositionSide.SHORT
        except (TypeError, ValueError):
            pass
        return PositionSide.LONG

    def get_position(self, symbol: str) -> Position | None:
        try:
            pos = self._client.get_open_position(symbol)
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

    def is_market_open(self, retries: int = 3, delay: float = 1.0) -> bool:
        """True only during the regular session.

        Retries on a transient error (e.g. a dropped connection) and only fails
        closed (False) if every attempt fails, so a brief network blip mid-session
        doesn't spuriously make us treat the market as closed and defer a cycle."""
        last_err = None
        for attempt in range(retries):
            try:
                return bool(self._client.get_clock().is_open)
            except Exception as e:
                last_err = e
                if attempt < retries - 1:
                    time.sleep(delay)
        logger.warning(f"Could not fetch market clock after {retries} tries: {last_err}")
        return False

    def is_shortable(self, symbol: str) -> bool:
        """F60: True only if Alpaca reports ``symbol`` tradable AND shortable AND
        easy_to_borrow. Fail-closed: any error (or missing flags) → False, so an
        unconfirmable name is never shorted. Cached for ``_etb_ttl`` seconds."""
        sym = symbol.upper()
        now = time.monotonic()
        hit = self._etb_cache.get(sym)
        if hit is not None and (now - hit[1]) < self._etb_ttl:
            return hit[0]
        try:
            asset = self._client.get_asset(sym)
        except Exception as e:  # fail-closed for THIS call, but do NOT cache a
            # transient failure — caching False would block the symbol for the
            # whole TTL after the API recovers. Only confirmed determinations are
            # cached (mirrors is_market_open: fail-closed, but retryable).
            logger.warning(f"is_shortable({sym}) check failed; treating as NOT shortable: {e}")
            return False
        ok = bool(
            getattr(asset, "tradable", False)
            and getattr(asset, "shortable", False)
            and getattr(asset, "easy_to_borrow", False)
        )
        self._etb_cache[sym] = (ok, now)
        return ok

    @staticmethod
    def _to_open_order(o, default_symbol: str | None = None) -> OpenOrder:
        side = OrderSide.BUY if str(o.side).split(".")[-1].lower() == "buy" else OrderSide.SELL
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

    def get_open_orders(self, symbol: str | None = None) -> list[OpenOrder]:
        """Open orders at Alpaca, including bracket/OCO protective legs.

        Uses ``nested=True`` and flattens each order's ``legs`` so the stop-loss
        leg of an OCO/bracket (held under the take-profit parent) is surfaced —
        needed for stop reconciliation, the ADJUST_STOP ratchet, and idempotency.
        """
        try:
            req = GetOrdersRequest(
                status=QueryOrderStatus.OPEN,
                symbols=[symbol] if symbol else None,
                nested=True,
            )
            orders = self._client.get_orders(filter=req)
        except Exception as e:
            logger.warning(f"Failed to fetch open orders: {e}")
            return []

        out: list[OpenOrder] = []
        seen: set[str] = set()
        for o in orders:
            for node in [o, *(getattr(o, "legs", None) or [])]:
                if str(node.id) in seen:
                    continue
                seen.add(str(node.id))
                out.append(self._to_open_order(node, default_symbol=o.symbol))
        return out

    def get_fills(self, since: str | None = None) -> list[FillEvent]:
        """Fill events from Alpaca's account-activities feed (Q3=A).

        alpaca-py's *Trading* client exposes no typed wrapper for
        ``GET /v2/account/activities`` (only the Broker client does), so this
        uses the inherited raw ``RESTClient.get`` (the SDK version-prefixes the
        path, so no leading ``/v2``). Keyed by the activity ``id`` so partial
        fills on one order stay distinct (idempotent cursor). ``since`` is an
        RFC3339 ``transaction_time`` cursor; dedup-by-id covers the same-timestamp
        boundary. Best-effort — failure returns [] (NFR-4). R1 verifies shape."""
        params: dict[str, str] = {"activity_types": "FILL"}
        if since:
            params["after"] = since
        try:
            raw = self._client.get("/account/activities", params)
        except Exception as e:  # never kill the publisher (NFR-4)
            logger.warning(f"get_fills (activities) failed: {e}")
            return []
        out: list[FillEvent] = []
        for a in raw if isinstance(raw, list) else []:
            ev = self._to_fill_event(a)
            if ev is not None:
                out.append(ev)
        return out

    @staticmethod
    def _to_fill_event(a: dict) -> FillEvent | None:
        """Parse one raw FILL activity dict into a FillEvent (tolerant)."""
        try:
            side = str(a.get("side", "")).lower()
            if side not in ("buy", "sell"):
                return None
            ts_raw = a.get("transaction_time") or a.get("date")
            ts = (
                datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                if ts_raw else datetime.now(timezone.utc)  # tz-aware fallback (review #3)
            )
            return FillEvent(
                fill_id=str(a["id"]),
                symbol=str(a["symbol"]),
                qty=abs(float(a.get("qty") or 0)),
                price=float(a.get("price") or 0),
                side=side,  # type: ignore[arg-type]
                kind="unknown",
                ts=ts,
            )
        except Exception as e:
            logger.warning(f"skipping unparseable activity {a!r}: {e}")
            return None

    def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        """F8: latest trade price per symbol via Alpaca market data (read-only,
        best-effort). Used to show current price + Δ-to-trigger for resting orders
        on symbols not currently held. Mirrors scripts/status.py. Failure → {}."""
        syms = [s for s in dict.fromkeys(symbols) if s]
        if not syms:
            return {}
        try:
            if self._data_client is None:
                from alpaca.data.historical import StockHistoricalDataClient
                self._data_client = StockHistoricalDataClient(self._api_key, self._secret_key)
                # F14: ctor timeout hook can't reach this lazily-built client — apply here.
                install_session_timeout(
                    self._data_client,
                    connect=self._http_connect_timeout,
                    read=self._http_read_timeout,
                )
            from alpaca.data.requests import StockLatestTradeRequest
            trades = self._data_client.get_stock_latest_trade(
                StockLatestTradeRequest(symbol_or_symbols=syms)
            )
            return {sym: float(tr.price) for sym, tr in trades.items()}
        except Exception as e:  # never kill the caller (NFR-4)
            logger.warning(f"get_latest_prices failed: {e}")
            return {}

    def get_all_positions(self) -> list[Position]:
        try:
            positions = self._client.get_all_positions()
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

    # ------------------------------------------------------------------ #
    # F9: structured order management (native Alpaca)
    # ------------------------------------------------------------------ #
    def replace_order(self, order_id: str, changes: dict) -> FilledOrder | None:
        """Native Alpaca replace of a resting SIMPLE order (Q2=A: the daemon
        rejects bracket/OCO-leg replaces upstream). ``changes`` may carry
        qty/limit_price/stop_price/trail/time_in_force. Returns the polled
        FilledOrder, or None on failure."""
        try:
            kwargs: dict = {}
            if changes.get("qty") is not None:
                kwargs["qty"] = int(changes["qty"])
            if changes.get("limit_price") is not None:
                kwargs["limit_price"] = float(changes["limit_price"])
            if changes.get("stop_price") is not None:
                kwargs["stop_price"] = float(changes["stop_price"])
            if changes.get("trail") is not None:
                kwargs["trail"] = float(changes["trail"])
            if changes.get("time_in_force") is not None:
                kwargs["time_in_force"] = self._tif_value(changes["time_in_force"])
            result = self._client.replace_order_by_id(order_id, ReplaceOrderRequest(**kwargs))
            logger.info(f"Order replaced: {order_id} -> {result.id} ({kwargs})")
            settled = self._poll_for_fill(str(result.id))
            side = OrderSide.BUY if str(settled.side).split(".")[-1].lower() == "buy" else OrderSide.SELL
            return FilledOrder(
                order_id=str(settled.id),
                symbol=settled.symbol,
                side=side,
                qty=float(settled.filled_qty or settled.qty or 0),
                filled_price=float(settled.filled_avg_price or 0),
                filled_at=settled.filled_at or datetime.now(),
            )
        except BrokerError:
            raise
        except Exception as e:
            logger.warning(f"Failed to replace order {order_id}: {e}")
            return None

    def cancel_all_orders(self, symbol: str | None = None) -> int:
        """Cancel all resting orders. No symbol -> native ``cancel_orders`` (one
        call); a symbol -> loop the base emulation over that symbol's opens."""
        if symbol is not None:
            return super().cancel_all_orders(symbol)
        try:
            resp = self._client.cancel_orders()
            n = len(resp) if resp is not None else 0
            logger.info(f"Cancelled all orders ({n})")
            return n
        except Exception as e:
            logger.warning(f"Failed to cancel all orders: {e}")
            return 0

    def record_trade_ledger(
        self,
        path: str | Path,
        *,
        since: str | None = None,
        min_notional: float = 0.0,
    ) -> None:
        """Reconstruct closed round-trips from the Alpaca activities/fills history
        and append them to the trades ledger at ``path``."""
        record_trades(self._client, path, since=since, min_notional=min_notional)

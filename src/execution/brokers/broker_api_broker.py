from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from loguru import logger

from src.agent.intraday.records import FillEvent
from src.agent.trades_log import record_trades
from src.core.exceptions import BrokerError
from src.core.models import FilledOrder, OpenOrder, Order, Position, PortfolioState
from src.core.types import OrderClass, OrderSide, OrderType, PositionSide
from src.execution.base import BaseBroker

try:
    from alpaca.broker.client import BrokerClient
    from alpaca.broker.requests import (  # envelope classes (critic #2)
        MarketOrderRequest,
        LimitOrderRequest,
        StopOrderRequest,
        StopLimitOrderRequest,
        GetAccountActivitiesRequest,
        CreateACHRelationshipRequest,
        CreateACHTransferRequest,
        OrderRequest,
    )
    from alpaca.broker.models.accounts import TradeAccount
    from alpaca.broker.models.funding import Transfer
    # Legs come from trading.requests (critic #2 — broker.requests has neither)
    from alpaca.trading.requests import (
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
        ActivityType,
    )
    from alpaca.trading.models import TradeActivity, NonTradeActivity
    from alpaca.common.enums import PaginationType
except ImportError:
    BrokerClient = None


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


class BrokerApiBroker(BaseBroker):
    """Broker implementation using Alpaca Broker API (sandbox).

    Talks to a single sandbox account identified by ``account_id`` through the
    per-account ``*_for_account`` endpoints.  The Trading API ``AlpacaBroker`` is
    the production paper/live path; this adapter unlocks the account farm created
    by ``scripts/broker_create_accounts.py``.

    Behaviour parity with ``AlpacaBroker`` so RiskManager / DecisionExecutor /
    the agent / the F8 sidebar are unchanged when this adapter is selected.
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        account_id: str,
        sandbox: bool = True,
        fill_poll_timeout: float = 5.0,
        fill_poll_interval: float = 0.2,
    ):
        if BrokerClient is None:
            raise BrokerError("alpaca-py not installed")

        # BR-1 / SECURITY-15: fail-closed on missing creds / account (P1).
        if not api_key or not secret_key:
            raise BrokerError("BROKER_API_KEY / BROKER_API_SECRET must be set")
        if not account_id:
            raise BrokerError("BROKER_ACCOUNT_ID must be set")

        self._account_id = str(account_id)
        self._api_key = api_key
        self._secret_key = secret_key
        self._c = BrokerClient(api_key, secret_key, sandbox=sandbox)
        self._fill_poll_timeout = fill_poll_timeout
        self._fill_poll_interval = fill_poll_interval
        self._data_client = None
        # F60: easy-to-borrow cache (only confirmed determinations cached).
        self._etb_cache: dict[str, tuple[bool, float]] = {}
        self._etb_ttl = 1800.0  # 30 min

        # Validate the account exists and capture the number for secure logging.
        acct = self._c.get_trade_account_by_id(self._account_id)
        self._account_number = acct.account_number
        self._masked_id = self._mask(self._account_id)
        logger.info(
            f"BrokerApiBroker initialized "
            f"(account={self._account_number}, id={self._masked_id}, sandbox=True)"
        )

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _mask(s: str, keep: int = 8) -> str:
        return s[:keep] + "…"

    def _poll_for_fill(self, order_id: str):
        """Poll an order until terminal status or timeout; return latest."""
        deadline = time.monotonic() + self._fill_poll_timeout
        latest = self._c.get_order_for_account_by_id(self._account_id, order_id)
        while time.monotonic() < deadline:
            status = str(latest.status).split(".")[-1].lower()
            if status in _TERMINAL_STATUSES:
                return latest
            time.sleep(self._fill_poll_interval)
            latest = self._c.get_order_for_account_by_id(self._account_id, order_id)
        return latest

    def _time_in_force(self, order: Order):
        if order.order_class in (OrderClass.BRACKET, OrderClass.OCO):
            return TimeInForce.GTC
        return (
            TimeInForce.GTC
            if str(order.time_in_force).lower() == "gtc"
            else TimeInForce.DAY
        )

    def _build_request(self, order: Order, side):
        """Mirror AlpacaBroker._build_request with broker envelope + trading legs.
        (critic #2: envelopes from broker.requests; legs from trading.requests)"""
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
                return LimitOrderRequest(limit_price=order.limit_price, **kwargs)
            return MarketOrderRequest(**kwargs)

        if order.order_class == OrderClass.OCO:
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

        if order.order_type == OrderType.MARKET:
            return MarketOrderRequest(
                symbol=order.symbol, qty=order.qty, side=side, time_in_force=tif
            )
        if order.order_type == OrderType.LIMIT:
            return LimitOrderRequest(
                symbol=order.symbol,
                qty=order.qty,
                side=side,
                time_in_force=tif,
                limit_price=order.limit_price,
            )
        if order.order_type == OrderType.STOP:
            return StopOrderRequest(
                symbol=order.symbol,
                qty=order.qty,
                side=side,
                time_in_force=tif,
                stop_price=order.stop_price,
            )
        if order.order_type == OrderType.STOP_LIMIT:
            return StopLimitOrderRequest(
                symbol=order.symbol,
                qty=order.qty,
                side=side,
                time_in_force=tif,
                limit_price=order.limit_price,
                stop_price=order.stop_price,
            )
        raise BrokerError(f"Unsupported order type: {order.order_type}")

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

    # ── orders ───────────────────────────────────────────────────────────

    def submit_order(self, order: Order) -> FilledOrder:
        try:
            side = AlpacaSide.BUY if order.side == OrderSide.BUY else AlpacaSide.SELL
            request = self._build_request(order, side)

            result = self._c.submit_order_for_account(self._account_id, request)
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
            o = self._c.get_order_for_account_by_id(self._account_id, order_id)
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
            self._c.cancel_order_for_account_by_id(self._account_id, order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to cancel order {order_id}: {e}")
            return False

    def get_open_orders(self, symbol: str | None = None) -> list[OpenOrder]:
        """Open orders at the Broker API, including bracket/OCO protective legs.

        Fetches ALL statuses (Broker API ``OPEN`` filter omits HELD legs and
        returns legs as top-level without the parent's nesting), then client-side
        filters out terminal statuses. ``nested=True`` + leg flattening so the
        stop-loss leg of an OCO/bracket is surfaced (parity with AlpacaBroker).
        """
        try:
            req = GetOrdersRequest(
                status=QueryOrderStatus.ALL,
                symbols=[symbol] if symbol else None,
                nested=True,
            )
            orders = self._c.get_orders_for_account(self._account_id, filter=req)
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
                status = str(getattr(node, "status", "")).split(".")[-1].lower()
                if status in _TERMINAL_STATUSES:
                    continue
                seen.add(sid)
                out.append(self._to_open_order(node, default_symbol=o.symbol))
        return out

    # ── positions / account ──────────────────────────────────────────────

    @staticmethod
    def _position_side(pos) -> PositionSide:
        """Map Alpaca's position side ('long'/'short') to ours; a short reports a
        negative qty which we normalize to positive (direction lives in side)."""
        raw = str(getattr(pos, "side", "")).split(".")[-1].lower()
        if raw == "short":
            return PositionSide.SHORT
        try:
            if float(pos.qty) < 0:
                return PositionSide.SHORT
        except (TypeError, ValueError):
            pass
        return PositionSide.LONG

    def get_position(self, symbol: str) -> Position | None:
        try:
            pos = self._c.get_open_position_for_account(self._account_id, symbol)
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
            positions = self._c.get_all_positions_for_account(self._account_id)
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
            account = self._c.get_trade_account_by_id(self._account_id)
            positions = self.get_all_positions()
            return PortfolioState(
                cash=float(account.cash),
                equity=float(account.equity),
                positions={p.symbol: p for p in positions},
            )
        except Exception as e:
            raise BrokerError(f"Failed to get portfolio state: {e}") from e

    def close_position(self, symbol: str) -> FilledOrder | None:
        try:
            result = self._c.close_position_for_account(self._account_id, symbol)
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

    # ── market clock ─────────────────────────────────────────────────────

    def is_market_open(self, retries: int = 3, delay: float = 1.0) -> bool:
        """True only during the regular session. Fail-closed (False) on error."""
        last_err = None
        for attempt in range(retries):
            try:
                return bool(self._c.get_clock().is_open)
            except Exception as e:
                last_err = e
                if attempt < retries - 1:
                    time.sleep(delay)
        logger.warning(
            f"Could not fetch market clock after {retries} tries: {last_err}"
        )
        return False

    def is_shortable(self, symbol: str) -> bool:
        """F60: True only if Alpaca reports ``symbol`` tradable AND shortable AND
        easy_to_borrow. Fail-closed (False) on error; a transient failure is NOT
        cached (would block the symbol for the whole TTL after recovery)."""
        sym = symbol.upper()
        now = time.monotonic()
        hit = self._etb_cache.get(sym)
        if hit is not None and (now - hit[1]) < self._etb_ttl:
            return hit[0]
        try:
            asset = self._c.get_asset(sym)
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

    # ── fills ────────────────────────────────────────────────────────────

    def get_fills(self, since: str | None = None) -> list[FillEvent]:
        """Fill events from the Broker API activities feed.

        Returns typed ``TradeActivity`` models (not raw dicts), so we use a
        dedicated typed mapper (critic #1 — NOT AlpacaBroker's dict parser).
        Pagination=FULL ensures no truncation (critic #7).
        """
        try:
            filter_req = GetAccountActivitiesRequest(
                account_id=UUID(self._account_id),
                activity_types=[ActivityType.FILL],
                # after=since handled below — GetAccountActivitiesRequest may
                # not carry an 'after' field; if not, paginate and filter.
            )
            activities = self._c.get_account_activities(
                filter_req,
                handle_pagination=PaginationType.FULL,
            )
        except Exception as e:
            logger.warning(f"get_fills (activities) failed: {e}")
            return []

        out: list[FillEvent] = []
        for a in activities:
            if since is not None:
                ts_raw = getattr(a, "transaction_time", None)
                if ts_raw and str(ts_raw) <= since:
                    continue
            ev = self._to_fill_event_typed(a)
            if ev is not None:
                out.append(ev)
        return out

    @staticmethod
    def _to_fill_event_typed(
        a,
    ) -> FillEvent | None:
        """Map a typed TradeActivity to a FillEvent (critic #1)."""
        if not isinstance(a, TradeActivity):
            return None
        try:
            side_str = str(a.side).split(".")[-1].lower()
            if side_str not in ("buy", "sell"):
                return None
            ts_raw = a.transaction_time
            ts = (
                datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                if ts_raw
                else datetime.now(timezone.utc)
            )
            return FillEvent(
                fill_id=str(a.id),
                symbol=str(a.symbol),
                qty=abs(float(a.qty or 0)),
                price=float(a.price or 0),
                side=side_str,
                kind="unknown",
                ts=ts,
            )
        except Exception as e:
            logger.warning(f"skipping unparseable activity {a!r}: {e}")
            return None

    # ── market data ──────────────────────────────────────────────────────

    def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        """Latest trade price per symbol via Broker API market data (sandbox).

        Uses ``StockHistoricalDataClient`` with ``use_basic_auth=True`` and a
        sandbox URL override (critic #3 — NOT AlpacaBroker's positional prod
        construction). Read-only, best-effort — never kills the caller.
        """
        syms = [s for s in dict.fromkeys(symbols) if s]
        if not syms:
            return {}
        try:
            if self._data_client is None:
                from alpaca.data.historical import StockHistoricalDataClient as S

                self._data_client = S(
                    api_key=self._api_key,
                    secret_key=self._secret_key,
                    use_basic_auth=True,
                    url_override="https://data.sandbox.alpaca.markets",
                )
            from alpaca.data.requests import StockLatestTradeRequest

            trades = self._data_client.get_stock_latest_trade(
                StockLatestTradeRequest(symbol_or_symbols=syms)
            )
            return {sym: float(tr.price) for sym, tr in trades.items()}
        except Exception as e:
            logger.warning(f"get_latest_prices failed: {e}")
            return {}

    # ── trade ledger ─────────────────────────────────────────────────────

    def record_trade_ledger(
        self,
        path: str | Path,
        *,
        since: str | None = None,
        min_notional: float = 0.0,
    ) -> None:
        """Reconstruct closed round-trips from Broker API fills and append
        to the trades ledger at ``path``.

        Uses a thin ``_LedgerClientShim`` so ``trades_log.record_trades`` is
        reused unchanged (P6 / critic verified-OK).
        """
        shim = _LedgerClientShim(self._c, self._account_id)
        record_trades(shim, path, since=since, min_notional=min_notional)


# ── record_trade_ledger shim ──────────────────────────────────────────


class _LedgerClientShim:
    """Exposes ONLY ``get_orders(filter=)`` → ``get_orders_for_account``
    so ``trades_log.record_trades`` works without change."""

    def __init__(self, client: BrokerClient, account_id: str):
        self._client = client
        self._account_id = account_id

    def get_orders(self, filter=None):
        return self._client.get_orders_for_account(self._account_id, filter=filter)

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from src.agent.intraday.records import FillEvent
from src.agent.trades_log import record_trades
from src.core.exceptions import BrokerError
from src.core.models import FilledOrder, Order
from src.core.types import OrderSide
from src.execution.brokers._alpaca_shaped import AlpacaShapedBroker
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
    )
    from alpaca.trading.enums import QueryOrderStatus
except ImportError:
    TradingClient = None
    MarketOrderRequest = LimitOrderRequest = StopOrderRequest = None
    StopLimitOrderRequest = TrailingStopOrderRequest = ReplaceOrderRequest = None
    QueryOrderStatus = None


class AlpacaBroker(AlpacaShapedBroker):
    """Broker implementation using the Alpaca **Trading API** (paper/live).

    Shares all request-building / fill-polling / position-mapping logic with
    ``BrokerApiBroker`` via ``AlpacaShapedBroker``; this class supplies only the
    Trading-API client hooks, request-envelope classes, the ``_extras`` passthrough,
    the raw-dict fills feed, and the native replace/cancel-all endpoints.
    """

    # SDK request-envelope classes (Trading API) — class attrs so request building
    # works even for ``__new__``-constructed instances (as the original module-level
    # names did). ``__init__`` only sets the per-instance open-orders query enum.
    _req_market = MarketOrderRequest
    _req_limit = LimitOrderRequest
    _req_stop = StopOrderRequest
    _req_stop_limit = StopLimitOrderRequest
    _req_trailing = TrailingStopOrderRequest

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
        # F8: keep keys to lazily build a market-data client for get_latest_prices.
        self._api_key = api_key
        self._secret_key = secret_key
        self._data_client = None
        # F60: easy-to-borrow cache (short TTL; only confirmed determinations cached).
        self._etb_cache: dict[str, tuple[bool, float]] = {}
        self._etb_ttl = 1800.0  # 30 min

        # Open-orders query enum (needs the imported enum; class attrs above cover
        # the request envelopes used by _build_request).
        self._open_orders_status = QueryOrderStatus.OPEN

        logger.info(f"AlpacaBroker initialized (paper={paper})")

    # ── behavioural override (D3): extended_hours / client_order_id passthrough ──

    def _extras(self, order: Order) -> dict:
        kw: dict = {}
        if order.extended_hours:
            kw["extended_hours"] = True
        if order.client_order_id:
            kw["client_order_id"] = order.client_order_id
        return kw

    # ── client hooks (Trading API) ──

    def _do_submit(self, request):
        return self._client.submit_order(request)

    def _do_get_order(self, order_id: str):
        return self._client.get_order_by_id(order_id)

    def _do_cancel(self, order_id: str) -> None:
        self._client.cancel_order_by_id(order_id)

    def _do_close(self, symbol: str):
        return self._client.close_position(symbol)

    def _do_get_open_position(self, symbol: str):
        return self._client.get_open_position(symbol)

    def _do_get_all_positions(self) -> list:
        return self._client.get_all_positions()

    def _do_get_account(self):
        return self._client.get_account()

    def _do_get_orders(self, filter):
        return self._client.get_orders(filter=filter)

    def _do_get_clock(self):
        return self._client.get_clock()

    def _do_get_asset(self, symbol: str):
        return self._client.get_asset(symbol)

    def _make_data_client(self):
        from alpaca.data.historical import StockHistoricalDataClient

        client = StockHistoricalDataClient(self._api_key, self._secret_key)
        # F14: ctor timeout hook can't reach this lazily-built client — apply here.
        install_session_timeout(
            client, connect=self._http_connect_timeout, read=self._http_read_timeout
        )
        return client

    # ── fills (raw-dict activities feed — Trading client has no typed wrapper) ──

    def get_fills(self, since: str | None = None) -> list[FillEvent]:
        """Fill events from Alpaca's account-activities feed (Q3=A).

        alpaca-py's *Trading* client exposes no typed wrapper for
        ``GET /v2/account/activities`` (only the Broker client does), so this uses
        the inherited raw ``RESTClient.get`` (the SDK version-prefixes the path).
        Keyed by the activity ``id`` (idempotent cursor). Best-effort — failure → []."""
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
                if ts_raw else datetime.now(timezone.utc)  # tz-aware fallback
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

    # ── F9: structured order management (native Alpaca) ──

    def replace_order(self, order_id: str, changes: dict) -> FilledOrder | None:
        """Native Alpaca replace of a resting SIMPLE order (Q2=A). ``changes`` may
        carry qty/limit_price/stop_price/trail/time_in_force. Returns the polled
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

    # ── trade ledger ──

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

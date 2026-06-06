from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from loguru import logger

from src.agent.intraday.records import FillEvent
from src.agent.trades_log import record_trades
from src.core.exceptions import BrokerError
from src.core.models import Order
from src.core.types import OrderClass, OrderSide
from src.execution.brokers._alpaca_shaped import AlpacaShapedBroker

try:
    from alpaca.broker.client import BrokerClient
    from alpaca.broker.requests import (  # order envelopes (critic #2)
        MarketOrderRequest,
        LimitOrderRequest,
        StopOrderRequest,
        StopLimitOrderRequest,
        GetAccountActivitiesRequest,
    )
    from alpaca.trading.enums import (
        OrderSide as AlpacaSide,
        QueryOrderStatus,
        TimeInForce,
        ActivityType,
    )
    from alpaca.trading.models import TradeActivity
    from alpaca.common.enums import PaginationType
except ImportError:
    BrokerClient = None
    MarketOrderRequest = LimitOrderRequest = StopOrderRequest = None
    StopLimitOrderRequest = GetAccountActivitiesRequest = None
    AlpacaSide = QueryOrderStatus = TimeInForce = ActivityType = None
    TradeActivity = PaginationType = None


class BrokerApiBroker(AlpacaShapedBroker):
    """Broker implementation using the Alpaca **Broker API** (sandbox account farm).

    Talks to a single sandbox account (``account_id``) through the per-account
    ``*_for_account`` endpoints, unlocking the account farm created by
    ``scripts/broker_create_accounts.py``. Shares all request-building / fill-polling
    / position-mapping logic with ``AlpacaBroker`` via ``AlpacaShapedBroker``; this
    class supplies only the Broker-API client hooks, request-envelope classes, the
    typed fills feed, and the ledger shim.

    Behaviour parity with ``AlpacaBroker`` (so RiskManager / DecisionExecutor / the
    agent / the F8 sidebar are unchanged when this adapter is selected) — with two
    deliberately-preserved divergences (R3 ledger T3-1/T3-2, fixed later in R7):
    the simpler side mapping and the lenient (non-fail-closed) TIF.
    """

    # Broker-API OPEN filter omits HELD legs and returns legs top-level; fetch ALL
    # and client-side drop terminal statuses (base ``get_open_orders`` honours this).
    _open_orders_skip_terminal = True

    # SDK request-envelope classes (Broker API) — class attrs so request building
    # works for ``__new__``-constructed instances too. ``_req_trailing`` stays None
    # (the Broker-API path doesn't build trailing stops).
    _req_market = MarketOrderRequest
    _req_limit = LimitOrderRequest
    _req_stop = StopOrderRequest
    _req_stop_limit = StopLimitOrderRequest
    _req_trailing = None

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

        # Open-orders query enum (needs the imported enum; class attrs above cover
        # the request envelopes used by _build_request).
        self._open_orders_status = QueryOrderStatus.ALL

        # Validate the account exists and capture the number for secure logging.
        acct = self._c.get_trade_account_by_id(self._account_id)
        self._account_number = acct.account_number
        self._masked_id = self._mask(self._account_id)
        logger.info(
            f"BrokerApiBroker initialized "
            f"(account={self._account_number}, id={self._masked_id}, sandbox=True)"
        )

    # ── helpers ──

    @staticmethod
    def _mask(s: str, keep: int = 8) -> str:
        return s[:keep] + "…"

    # ── behavioural overrides (preserved divergences; R3 T3-1 / T3-2) ──

    @staticmethod
    def _alpaca_side(side: OrderSide):
        # T3-1 (preserved): current simple mapping. NOTE BUY_TO_COVER falls into the
        # else branch → SELL (a latent bug). The correct mapping is adopted in R7.
        return AlpacaSide.BUY if side == OrderSide.BUY else AlpacaSide.SELL

    def _time_in_force(self, order: Order):
        # T3-2 (preserved): GTC for protective legs; otherwise gtc→GTC else→DAY
        # (silent downgrade rather than fail-closed; tightened in R7).
        if order.order_class in (OrderClass.BRACKET, OrderClass.OCO):
            return TimeInForce.GTC
        return (
            TimeInForce.GTC
            if str(order.time_in_force).lower() == "gtc"
            else TimeInForce.DAY
        )

    # ── client hooks (Broker API, per-account endpoints) ──

    def _do_submit(self, request):
        return self._c.submit_order_for_account(self._account_id, request)

    def _do_get_order(self, order_id: str):
        return self._c.get_order_for_account_by_id(self._account_id, order_id)

    def _do_cancel(self, order_id: str) -> None:
        self._c.cancel_order_for_account_by_id(self._account_id, order_id)

    def _do_close(self, symbol: str):
        return self._c.close_position_for_account(self._account_id, symbol)

    def _do_get_open_position(self, symbol: str):
        return self._c.get_open_position_for_account(self._account_id, symbol)

    def _do_get_all_positions(self) -> list:
        return self._c.get_all_positions_for_account(self._account_id)

    def _do_get_account(self):
        return self._c.get_trade_account_by_id(self._account_id)

    def _do_get_orders(self, filter):
        return self._c.get_orders_for_account(self._account_id, filter=filter)

    def _do_get_clock(self):
        return self._c.get_clock()

    def _do_get_asset(self, symbol: str):
        return self._c.get_asset(symbol)

    def _make_data_client(self):
        from alpaca.data.historical import StockHistoricalDataClient

        # critic #3: sandbox needs basic-auth + a sandbox URL override (NOT the prod
        # positional construction AlpacaBroker uses).
        return StockHistoricalDataClient(
            api_key=self._api_key,
            secret_key=self._secret_key,
            use_basic_auth=True,
            url_override="https://data.sandbox.alpaca.markets",
        )

    # ── fills (typed TradeActivity feed) ──

    def get_fills(self, since: str | None = None) -> list[FillEvent]:
        """Fill events from the Broker API activities feed.

        Returns typed ``TradeActivity`` models (critic #1 — NOT AlpacaBroker's dict
        parser). Pagination=FULL ensures no truncation (critic #7)."""
        try:
            filter_req = GetAccountActivitiesRequest(
                account_id=UUID(self._account_id),
                activity_types=[ActivityType.FILL],
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
    def _to_fill_event_typed(a) -> FillEvent | None:
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

    # ── trade ledger ──

    def record_trade_ledger(
        self,
        path: str | Path,
        *,
        since: str | None = None,
        min_notional: float = 0.0,
    ) -> None:
        """Reconstruct closed round-trips from Broker API fills and append to the
        trades ledger at ``path``. Uses a thin ``_LedgerClientShim`` so
        ``trades_log.record_trades`` is reused unchanged (P6)."""
        shim = _LedgerClientShim(self._c, self._account_id)
        record_trades(shim, path, since=since, min_notional=min_notional)


class _LedgerClientShim:
    """Exposes ONLY ``get_orders(filter=)`` → ``get_orders_for_account`` so
    ``trades_log.record_trades`` works without change."""

    def __init__(self, client, account_id: str):
        self._client = client
        self._account_id = account_id

    def get_orders(self, filter=None):
        return self._client.get_orders_for_account(self._account_id, filter=filter)

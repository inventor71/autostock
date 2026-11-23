"""Alpaca-shaped access to Toss's US cash-equity account slice.

Toss's OCO is limit-only and cancels its sibling on trigger, not fill. It is
not equivalent to Autostock's stop-market brackets. Reject those orders before
any mutation; do not silently substitute weaker protection or local polling.
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo

from src.core.exceptions import BrokerError
from src.core.models import FilledOrder, OpenOrder, Order, PortfolioState, Position
from src.core.types import OrderClass, OrderSide, OrderType
from src.execution.base import BaseBroker
from src.execution.brokers.toss.client import TossAPIError, TossClient


class TossPortfolioState(PortfolioState):
    currency: str = "USD"
    valuation_basis: Literal["available_cash_plus_positions"] = "available_cash_plus_positions"


def decimal_value(value, name: str, *, positive=False) -> Decimal:
    try:
        result = Decimal(str(value))
        if not result.is_finite() or (positive and result <= 0):
            raise ValueError
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise BrokerError(f"Invalid Toss {name}") from None


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise BrokerError("Toss timestamp must include a timezone")
    return result


class TossBroker(BaseBroker):
    supports_bracket_orders = False

    def __init__(self, client: TossClient, *, fill_poll_timeout: float = 2.0):
        if not client.credentials.account_seq:
            raise BrokerError("A Toss account must be selected before creating the broker")
        self.client = client
        self._fill_poll_timeout = fill_poll_timeout
        self._stock_cache: dict[str, tuple[float, dict]] = {}

    def close(self):
        self.client.close()

    def get_cost_profile(self):
        from src.execution.brokers.toss.costs import CommissionSchedule
        return {"commission": CommissionSchedule(self.client).get(),
                "annual_capital_gains_tax_included": False,
                "note": "Commission rate only; execution fees/taxes are reported by Toss on fills"}

    def _write_enabled(self):
        if self.client.read_only:
            raise BrokerError("Toss is read-only; account linking does not enable live orders")

    def _stock(self, symbol: str) -> dict:
        symbol = symbol.upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,19}", symbol):
            raise BrokerError("Toss broker currently supports US symbols only")
        cached = self._stock_cache.get(symbol)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        rows = self.client.request("GET", "/api/v1/stocks", params={"symbols": symbol})
        stock = next((row for row in rows if row["symbol"] == symbol), None)
        if not stock or stock["currency"] != "USD" or stock["status"] != "ACTIVE":
            raise BrokerError("Toss trading requires an active US stock denominated in USD")
        self._stock_cache[symbol] = (time.monotonic() + 300, stock)
        return stock

    def validate_order(self, order: Order) -> None:
        self._write_enabled()
        if order.order_class != OrderClass.SIMPLE:
            raise BrokerError(
                "Toss does not provide equivalent stop-market BRACKET/OCO/OTO protection; "
                "this order is unsupported and no entry was submitted"
            )
        if order.side not in (OrderSide.BUY, OrderSide.SELL):
            raise BrokerError("Toss short selling is unsupported")
        if order.order_type not in (OrderType.MARKET, OrderType.LIMIT):
            raise BrokerError("Toss adapter supports ordinary MARKET/LIMIT orders only")
        if order.time_in_force.lower() != "day" or order.extended_hours:
            raise BrokerError("Toss adapter supports DAY orders during the regular session only")
        if any(v is not None for v in (
            order.stop_price, order.stop_loss_price, order.take_profit_price,
            order.trail_price, order.trail_percent,
        )):
            raise BrokerError("Toss simple orders cannot silently discard protective fields")
        qty = decimal_value(order.qty, "quantity", positive=True)
        if qty != qty.to_integral_value():
            if order.side != OrderSide.SELL or order.order_type != OrderType.MARKET:
                raise BrokerError("Toss fractional quantities are only supported for market sells")
            if qty.as_tuple().exponent < -6:
                raise BrokerError("Toss fractional quantities support at most six decimal places")
        if order.order_type == OrderType.LIMIT:
            price = decimal_value(order.limit_price, "limit price", positive=True)
            step = Decimal("0.01") if price >= 1 else Decimal("0.0001")
            if price % step:
                raise BrokerError("Toss limit price exceeds supported precision; choose an exact price")
        elif order.limit_price is not None:
            raise BrokerError("Toss MARKET orders cannot include a limit price")
        if order.client_order_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,36}", order.client_order_id):
            raise BrokerError("Invalid Toss client_order_id")

    def submit_order(self, order: Order) -> FilledOrder:
        self.validate_order(order)
        if order.side == OrderSide.BUY:
            # A stale promotion must not silently fund a new exposure decision.
            # Risk-reducing sells remain available when fee discovery is down.
            self.get_cost_profile()
        symbol = order.symbol.upper()
        self._stock(symbol)
        if not self.is_market_open():
            raise BrokerError("Toss orders are restricted to the regular US session")
        if order.side == OrderSide.SELL:
            sellable = self.client.request(
                "GET", "/api/v1/sellable-quantity", params={"symbol": symbol}, account=True,
            )
            if decimal_value(order.qty, "quantity") > decimal_value(
                sellable["sellableQuantity"], "sellable quantity"
            ):
                raise BrokerError("Toss sell quantity exceeds available holdings")
        if not order.client_order_id:
            order.client_order_id = str(uuid.uuid4())
        payload = {
            "symbol": symbol, "side": order.side.value.upper(),
            "orderType": order.order_type.value.upper(), "timeInForce": "DAY",
            "quantity": format(decimal_value(order.qty, "quantity").normalize(), "f"),
            "clientOrderId": order.client_order_id,
        }
        if order.order_type == OrderType.LIMIT:
            payload["price"] = format(decimal_value(order.limit_price, "limit price"), "f")
        result = self.client.create_order(payload)
        order_id = str(result["orderId"])
        # Submission acceptance is not a fill. If the follow-up read fails, keep
        # the accepted ID and qty=0, allowing later reconciliation without a buy retry.
        pending = FilledOrder(
            order_id=order_id, symbol=symbol, side=order.side, qty=0, filled_price=0,
            filled_at=datetime.now(UTC),
        )
        deadline = time.monotonic() + self._fill_poll_timeout
        while True:
            try:
                row = self._order(order_id)
            except BrokerError:
                return pending
            if row is not None:
                pending = self._filled(row)
                if row["status"] == "REJECTED" and pending.qty == 0:
                    raise BrokerError("Toss rejected the submitted order; check order history")
                if pending.qty > 0 or row["status"] in {"CANCELED", "REPLACED", "FILLED"}:
                    return pending
            if time.monotonic() >= deadline:
                return pending
            time.sleep(0.3)

    def _order(self, order_id: str) -> dict | None:
        try:
            return self.client.request(
                "GET", f"/api/v1/orders/{quote(order_id, safe='')}", account=True,
            )
        except TossAPIError as error:
            if error.status == 404 and error.code == "order-not-found":
                return None
            raise

    @staticmethod
    def _filled(row: dict) -> FilledOrder:
        execution = row["execution"]
        qty = decimal_value(execution["filledQuantity"], "filled quantity")
        price = decimal_value(execution.get("averageFilledPrice") or 0, "fill price")
        if qty < 0 or (qty > 0 and price <= 0):
            raise BrokerError("Toss returned inconsistent execution amounts")
        return FilledOrder(
            order_id=row["orderId"], symbol=row["symbol"], side=OrderSide(row["side"].lower()),
            qty=float(qty), filled_price=float(price),
            filled_at=_time(execution.get("filledAt") or row["orderedAt"]),
            commission=float(decimal_value(execution.get("commission") or 0, "commission")
                             + decimal_value(execution.get("tax") or 0, "tax")),
        )

    def get_order_status(self, order_id: str) -> FilledOrder | None:
        row = self._order(order_id)
        if row is None:
            return None
        if row["currency"] != "USD":
            raise BrokerError("Toss broker cannot mix KRW orders into a USD portfolio")
        return self._filled(row)

    def get_conditional_orders(self, symbol: str | None = None) -> list[dict]:
        params = {"status": "OPEN"}
        if symbol:
            params["symbol"] = symbol.upper()
        return [row for row in self.client.pages(
            "/api/v1/conditional-orders", "conditionalOrders", params=params,
        ) if row["market"] == "US"]

    def get_open_orders(self, symbol: str | None = None) -> list[OpenOrder]:
        params = {"status": "OPEN"}
        if symbol:
            params["symbol"] = symbol.upper()
        rows = self.client.pages("/api/v1/orders", "orders", params=params)
        result = []
        for row in rows:
            if row["currency"] != "USD":
                continue
            try:
                order_type = OrderType(row["orderType"].lower())
                side = OrderSide(row["side"].lower())
            except ValueError:
                raise BrokerError("Unknown Toss order type; inspect orders in Toss before trading") from None
            result.append(OpenOrder(
                order_id=row["orderId"], symbol=row["symbol"], side=side, order_type=order_type,
                qty=float(decimal_value(row["quantity"], "quantity")
                          - decimal_value(row["execution"]["filledQuantity"], "filled quantity")),
                limit_price=float(row["price"]) if row.get("price") is not None else None,
            ))
        # Do not hide app-created conditional orders from cancel/close callers.
        # They cannot be represented faithfully by the shared OpenOrder model.
        if self.get_conditional_orders(symbol):
            raise BrokerError(
                "Active Toss conditional orders require management in Toss; "
                "the Alpaca-shaped open-order list would be incomplete"
            )
        return result

    def cancel_order(self, order_id: str) -> bool:
        self._write_enabled()
        row = self._order(order_id)
        if row is None:
            return False
        if row["currency"] != "USD":
            raise BrokerError("Toss broker only manages US orders")
        if row["status"] == "CANCELED":
            return True
        if row["status"] in {"FILLED", "REJECTED", "REPLACED"}:
            return False
        self.client.request("POST", f"/api/v1/orders/{quote(order_id, safe='')}/cancel", account=True)
        # A cancel ACK has a new operation ID; it does NOT confirm the original
        # order is canceled. Check the original before releasing its reserved qty.
        deadline = time.monotonic() + self.cancel_settle_wait
        while True:
            current = self._order(order_id)
            if current and current["status"] == "CANCELED":
                return True
            if current and current["status"] in {"FILLED", "REJECTED", "REPLACED"}:
                return False
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.3)

    def replace_order(self, order_id: str, changes: dict) -> FilledOrder | None:
        self._write_enabled()
        # US modify cannot change quantity. Reject it, even if equal to current.
        if not changes or set(changes) != {"limit_price"}:
            raise BrokerError("Toss US replace supports limit_price only; quantity changes are unsupported")
        row = self._order(order_id)
        if row is None:
            return None
        if row["currency"] != "USD" or row["orderType"] != "LIMIT":
            raise BrokerError("Toss replace requires a US limit order")
        if row["timeInForce"] != "DAY" or row["status"] not in {"PENDING", "PARTIAL_FILLED"}:
            raise BrokerError("Toss replace requires an active ordinary DAY order")
        order = Order(
            symbol=row["symbol"], side=OrderSide(row["side"].lower()), qty=float(row["quantity"]),
            order_type=OrderType.LIMIT, limit_price=changes["limit_price"],
        )
        self.validate_order(order)
        if not self.is_market_open():
            raise BrokerError("Toss order replacement is restricted to the regular US session")
        result = self.client.request(
            "POST", f"/api/v1/orders/{quote(order_id, safe='')}/modify", account=True,
            body={"orderType": "LIMIT", "price": format(Decimal(str(order.limit_price)), "f")},
        )
        new_id = str(result["orderId"])
        try:
            filled = self.get_order_status(new_id)
        except BrokerError:
            filled = None
        return filled or FilledOrder(
            order_id=new_id, symbol=order.symbol, side=order.side, qty=0, filled_price=0,
            filled_at=datetime.now(UTC),
        )

    def get_all_positions(self) -> list[Position]:
        rows = self.client.request("GET", "/api/v1/holdings", account=True)["items"]
        result = []
        for row in rows:
            if row["currency"] != "USD" or row["marketCountry"] != "US":
                continue
            qty = decimal_value(row["quantity"], "holding quantity")
            if qty < 0:
                raise BrokerError("Toss adapter does not support short positions")
            if qty:
                result.append(Position(
                    symbol=row["symbol"], qty=float(qty),
                    avg_entry_price=float(decimal_value(row["averagePurchasePrice"], "purchase price")),
                    current_price=float(decimal_value(row["lastPrice"], "price")),
                    market_value=float(decimal_value(row["marketValue"]["amount"], "market value")),
                    unrealized_pnl=float(decimal_value(row["profitLoss"]["amount"], "profit/loss")),
                ))
        return result

    def get_position(self, symbol: str) -> Position | None:
        return next((p for p in self.get_all_positions() if p.symbol == symbol.upper()), None)

    def get_portfolio_state(self) -> TossPortfolioState:
        """Conservative USD capital estimate, NOT total account equity/return NAV.

        Cash buying power may exclude reserved/unsettled funds. No KRW assets or
        FX are added; the API does not expose the cash ledger needed for full NAV.
        """
        positions = {p.symbol: p for p in self.get_all_positions()}
        buying = self.client.request(
            "GET", "/api/v1/buying-power", params={"currency": "USD"}, account=True,
        )
        if buying["currency"] != "USD":
            raise BrokerError("Toss buying power must be in USD")
        cash = float(decimal_value(buying["cashBuyingPower"], "buying power"))
        return TossPortfolioState(
            cash=cash, equity=cash + sum(p.market_value for p in positions.values()),
            positions=positions, timestamp=datetime.now(UTC),
        )

    def close_position(self, symbol: str) -> FilledOrder | None:
        self._write_enabled()
        # Fail before cancellation if unsupported conditional protection exists.
        opens = self.get_open_orders(symbol)
        for order in opens:
            if not self.cancel_order(order.order_id):
                raise BrokerError("Toss close aborted: cancellation has not been confirmed")
        position = self.get_position(symbol)
        if position is None:
            return None
        return self.submit_order(Order(symbol=symbol, side=OrderSide.SELL, qty=position.qty))

    def is_shortable(self, symbol: str) -> bool:
        return False

    def is_market_open(self) -> bool:
        now = datetime.now(UTC)
        today = now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        result = self.client.request("GET", "/api/v1/market-calendar/US", params={"date": today})
        session = result["today"].get("regularMarket")
        return bool(session and _time(session["startTime"]) <= now < _time(session["endTime"]))

    def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        from src.data.providers.toss_provider import TossDataProvider
        return TossDataProvider(self.client).get_latest_prices(symbols)

"""Durable, local USD shadow account. The only remote operations are Toss GETs.

This is a quote-driven counterfactual, not a Toss paper endpoint. Virtual stop
orders are polled and can gap. Every fill retains its observed book and costs.
"""
from __future__ import annotations

import copy
import json
import math
import re
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.agent.intraday.records import FillEvent
from src.core.exceptions import BrokerError
from src.core.models import FilledOrder, OpenOrder, Order, PortfolioState, Position
from src.core.types import OrderClass, OrderSide, OrderType
from src.execution.base import BaseBroker
from src.execution.brokers.toss import storage
from src.execution.brokers.toss.broker import TossBroker, _time, normalize_market_sell
from src.execution.brokers.toss.costs import ET, CommissionSchedule, TossCosts, number
from src.execution.brokers.toss.quality import quote_quality, record_session

OPEN = {"open", "partial"}
ASSUMPTIONS = [
    "USD available cash + US positions only; not full Toss account NAV",
    "Seed once; actual subsequent trades/deposits are not mirrored",
    "Toss venue quotes are not consolidated NBBO; queue position/market impact are unknown",
    "Virtual stop/OCO protection only; live Toss autonomous brackets remain disabled",
    "Polled quotes, adverse slippage, bounded displayed liquidity; fills are hypothetical",
    "Cancels are local and immediate; real cancellation/routing latency is not measured",
    "Sale proceeds are immediately reusable in this cash model; settlement restrictions are not modeled",
    "No FX, annual capital-gains tax, dividends, splits, mergers or ADR/corporate-action fees",
]


def _positive(value) -> float:
    result = float(number(value))
    if result <= 0 or not math.isfinite(result):
        raise BrokerError("Shadow price/quantity must be positive and finite")
    return result


def parse_book(row: dict, observed: datetime) -> dict:
    """Validate feed shape separately from the stricter execution-age check."""
    try:
        source = _time(row["timestamp"])
        if row["currency"] != "USD" or source > observed + timedelta(seconds=2):
            raise ValueError
        sides = {}
        for side in ("asks", "bids"):
            levels = [{"price": _positive(r["price"]), "volume": float(number(r["volume"]))}
                      for r in row[side] if number(r["volume"]) > 0]
            if not levels or len({r["price"] for r in levels}) != len(levels):
                raise ValueError
            sides[side] = sorted(levels, key=lambda r: r["price"], reverse=side == "bids")
        if sides["asks"][0]["price"] < sides["bids"][0]["price"]:
            raise ValueError
        return {**sides, "source_at": source.isoformat(), "observed_at": observed.isoformat()}
    except (ValueError, KeyError, TypeError):
        raise BrokerError("Missing, crossed or invalid USD orderbook") from None


class TossShadowBroker(BaseBroker):
    supports_bracket_orders = True  # virtual, NOT a claim about Toss capabilities
    cancel_settle_wait = 0.0
    simulation = True

    def __init__(self, client, root: str | Path, *, clock=None):
        if not client.read_only:
            raise BrokerError("Shadow mode requires a read-only Toss client")
        self.client = client
        self.root = Path(root).expanduser().absolute()
        self.path = self.root / "account.json"
        self.clock = clock or (lambda: datetime.now(UTC))
        self.costs = TossCosts(CommissionSchedule(client, clock=self.clock))
        self.decision_key: str | None = None
        self._calendar = None

    def close(self):
        self.client.close()

    def read(self) -> dict:
        state = storage.read_json(self.path)
        if state.get("version") != 1:
            raise BrokerError("Initialize a new Toss shadow run first; never recreate a missing ledger")
        if state.get("source_identity") != self.costs.schedule.path.stem:
            raise BrokerError("Shadow run belongs to a different Toss account connection")
        return state

    @contextmanager
    def transaction(self):
        with storage.locked(self.root / "account.lock"):
            state = self.read()
            yield state
            storage.write_json(self.path, state)

    def initialize(self, *, days=7, latency_seconds=1.0, slippage_bps=2.0,
                   participation=0.1, max_quote_age=15.0, symbols=None, runtime=None):
        if not (1 <= days <= 30 and 0 < participation <= 1 and
                0 <= slippage_bps <= 100 and 0 < latency_seconds <= 60 and
                0 < max_quote_age <= 60):
            raise BrokerError("Invalid shadow duration/execution assumptions")
        with storage.locked(self.root / "account.lock"):
            if self.path.exists():
                raise BrokerError("Shadow run already exists; choose a new directory instead of resetting it")
            source = TossBroker(self.client).get_portfolio_state()
            profile = self.costs.profile()
            now = self.clock()
            positions = {}
            marks = {}
            for symbol, position in source.positions.items():
                positions[symbol] = {"qty": _positive(position.qty),
                                     "avg_entry_price": float(number(position.avg_entry_price))}
                marks[symbol] = {"price": _positive(position.current_price),
                                 "source_at": None, "observed_at": now.isoformat()}
            cash = float(number(source.cash))
            equity = cash + sum(p["qty"] * marks[s]["price"] for s, p in positions.items())
            if equity <= 0:
                raise BrokerError("Shadow seed must have positive USD capital")
            universe = sorted(set(symbols or []) | set(positions))
            if not universe or any(not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,19}", s) for s in universe):
                raise BrokerError("Provide a nonempty US symbol universe")
            state = {"version": 1, "source_identity": self.costs.schedule.path.stem,
                     "created_at": now.isoformat(),
                     "end_at": (now + timedelta(days=days)).isoformat(),
                     "cash": cash, "positions": positions, "marks": marks,
                     "initial": {"cash": cash, "positions": copy.deepcopy(positions), "equity": equity},
                     "orders": {}, "fills": [], "book_usage": {}, "turns": [], "universe": universe,
                     "cost_profile": profile, "assumptions": ASSUMPTIONS,
                     "execution": {"latency_seconds": latency_seconds, "slippage_bps": slippage_bps,
                                   "participation": participation, "max_quote_age": max_quote_age},
                     "health": {"status": "initialized", "as_of": now.isoformat()},
                     "metrics": {"peak_equity": equity, "max_drawdown_pct": 0.0,
                                 "polls": 0, "blocked_polls": 0, "snapshots": 0, "valid_snapshots": 0}}
            if runtime is not None:
                state.update({key: runtime[key] for key in ("agent_config", "risk_config", "runner")})
            storage.write_json(self.path, state)
        return self.report()

    def get_cost_profile(self):
        return {**self.costs.profile(), "simulation": True}

    def is_market_open(self) -> bool:
        now = self.clock()
        if self._calendar is None or (now - self._calendar[0]).total_seconds() >= 60:
            row = self.client.request("GET", "/api/v1/market-calendar/US",
                                      params={"date": now.astimezone(ET).date().isoformat()})
            self._calendar = (now, row["today"].get("regularMarket"))
        return self._session_open(now)

    def _session_open(self, now):
        session = self._calendar[1]
        return bool(session and _time(session["startTime"]) <= now < _time(session["endTime"]))

    def is_shortable(self, symbol):
        return False

    def validate_order(self, order):
        _positive(order.qty)
        if round(order.qty, 6) != order.qty:
            raise BrokerError("Toss quantity precision is at most six decimals")
        if order.side not in (OrderSide.BUY, OrderSide.SELL) or order.extended_hours:
            raise BrokerError("Toss shadow supports regular-session long-only orders")
        if order.order_class not in (OrderClass.SIMPLE, OrderClass.BRACKET, OrderClass.OCO):
            raise BrokerError("Unsupported shadow order class")
        if order.order_type not in (OrderType.MARKET, OrderType.LIMIT, OrderType.STOP):
            raise BrokerError("Unsupported shadow order type")
        if order.side == OrderSide.BUY and (not float(order.qty).is_integer() or
                order.order_type == OrderType.STOP or order.order_class == OrderClass.OCO):
            raise BrokerError("Toss buys require whole shares and MARKET/LIMIT orders")
        if order.order_class == OrderClass.BRACKET and order.side != OrderSide.BUY:
            raise BrokerError("Shadow brackets open a long position")
        if str(order.time_in_force).lower() not in {"day", "gtc"}:
            raise BrokerError("Shadow supports DAY entries and virtual GTC protection")
        if order.order_type == OrderType.LIMIT:
            _positive(order.limit_price)
        if order.order_type == OrderType.STOP:
            _positive(order.stop_price)
        for value in (order.take_profit_price, order.stop_loss_price):
            if value is not None:
                _positive(value)
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,19}", order.symbol):
            raise BrokerError("Invalid US symbol")
        if order.order_class == OrderClass.OCO or (order.side == OrderSide.SELL and order.order_type == OrderType.STOP):
            stop = order.stop_loss_price if order.order_class == OrderClass.OCO else order.stop_price
            _positive(stop)
            if order.order_class == OrderClass.OCO:
                _positive(order.take_profit_price)
            book = parse_book(self.client.request("GET", "/api/v1/orderbook",
                              params={"symbol": order.symbol}), self.clock())
            age = (self.clock() - _time(book["source_at"])).total_seconds()
            if not 0 <= age <= self.read()["execution"]["max_quote_age"]:
                raise BrokerError("Fresh quote required for new protection")
            if stop >= book["bids"][0]["price"] or (order.order_class == OrderClass.OCO
                    and order.take_profit_price <= book["asks"][0]["price"]):
                raise BrokerError("Protection already crossed the current quote; re-evaluate or request an explicit SELL")

    def _row(self, order, oid, now, *, group=None, protective=False):
        return {"id": oid, "order": order.model_dump(mode="json"), "status": "open",
                "submitted_at": now.isoformat(), "ready_at": now.isoformat(),
                "day": now.astimezone(ET).date().isoformat(), "filled_qty": 0.0,
                "filled_notional": 0.0, "commission": 0.0, "regulatory": 0.0,
                "commission_basis": "0", "regulatory_basis": "0", "reserve_unit": 0.0,
                "group": group, "protective": protective, "triggered": False}

    def _protect(self, state, symbol, qty, stop, target, group, now):
        for suffix, kind, price in (("stop", OrderType.STOP, stop), ("target", OrderType.LIMIT, target)):
            oid = group + ":" + suffix
            if oid in state["orders"] and state["orders"][oid]["status"] in OPEN:
                state["orders"][oid]["order"]["qty"] += qty
                continue
            order = Order(symbol=symbol, side=OrderSide.SELL, qty=qty, order_type=kind,
                          stop_price=price if kind == OrderType.STOP else None,
                          limit_price=price if kind == OrderType.LIMIT else None, time_in_force="gtc")
            row = self._row(order, oid, now, group=group, protective=True)
            row["ready_at"] = (now + timedelta(seconds=state["execution"]["latency_seconds"])).isoformat()
            state["orders"][oid] = row

    def submit_order(self, order):
        normalize_market_sell(order)
        self.validate_order(order)
        if not self.is_market_open():
            raise BrokerError("Shadow orders require an open regular US session")
        profile = self.costs.profile()
        oid = self.decision_key or order.client_order_id or "shadow-" + uuid.uuid4().hex
        reference = None
        if order.side == OrderSide.BUY:
            reference = parse_book(self.client.request("GET", "/api/v1/orderbook",
                                   params={"symbol": order.symbol}), self.clock())
        with self.transaction() as state:
            now = self.clock()
            if oid in state["orders"]:
                if state["orders"][oid]["order"] != order.model_dump(mode="json"):
                    raise BrokerError("Conflicting shadow order identity")
                return self._filled(state["orders"][oid])
            if now >= _time(profile["commission"]["next_check_at"]):
                profile = self.costs.profile()
            now = self.clock()
            if now >= _time(state["end_at"]):
                raise BrokerError("Shadow experiment has ended")
            if order.symbol not in state["universe"]:
                raise BrokerError("Symbol is outside the frozen shadow universe")
            if order.side == OrderSide.SELL:
                held = state["positions"].get(order.symbol, {}).get("qty", 0)
                if order.qty > held + 1e-8:
                    raise BrokerError("Shadow sells cannot exceed holdings")
            row = self._row(order, oid, now,
                            protective=order.side == OrderSide.SELL and order.order_type == OrderType.STOP)
            if reference is not None and order.side == OrderSide.BUY:
                age = (now - _time(reference["source_at"])).total_seconds()
                if not 0 <= age <= state["execution"]["max_quote_age"]:
                    raise BrokerError("Fresh quote required to reserve shadow cash")
                price = order.limit_price or reference["asks"][0]["price"] * 1.01
                row["reserve_unit"] = price * (1 + float(profile["commission"]["rate"]))
                reserve = row["reserve_unit"] * order.qty + 0.01
                if reserve > state["cash"] - self._reserved(state) + 1e-8:
                    raise BrokerError("Insufficient unreserved shadow cash")
            row["ready_at"] = (now + timedelta(seconds=state["execution"]["latency_seconds"])).isoformat()
            if order.order_class == OrderClass.OCO:
                row["status"] = "accepted_protection"
                self._protect(state, order.symbol, order.qty, order.stop_loss_price,
                              order.take_profit_price, oid, now)
            state["orders"][oid] = row
            state["cost_profile"] = profile
            return self._filled(row)

    @staticmethod
    def _filled(row):
        qty = row["filled_qty"]
        return FilledOrder(order_id=row["id"], symbol=row["order"]["symbol"],
                           side=row["order"]["side"], qty=qty,
                           filled_price=row["filled_notional"] / qty if qty else 0,
                           filled_at=_time(row.get("filled_at", row["submitted_at"])),
                           commission=row["commission"] + row["regulatory"])

    def get_order_status(self, order_id):
        row = self.read()["orders"].get(order_id)
        return self._filled(row) if row else None

    def get_open_orders(self, symbol=None):
        return [OpenOrder(order_id=r["id"], symbol=r["order"]["symbol"], side=r["order"]["side"],
                          order_type=r["order"]["order_type"], qty=r["order"]["qty"] - r["filled_qty"],
                          limit_price=r["order"]["limit_price"], stop_price=r["order"]["stop_price"])
                for r in self.read()["orders"].values()
                if r["status"] in OPEN and (symbol is None or r["order"]["symbol"] == symbol)]

    def cancel_order(self, order_id):
        with self.transaction() as state:
            row = state["orders"].get(order_id)
            if not row or row["status"] not in OPEN:
                return False
            row["status"] = "canceled"
            # Canceling a protective leg cancels its OCO peer; canceling an entry
            # remainder deliberately preserves protection for its partial fills.
            if row["group"]:
                for peer in state["orders"].values():
                    if peer["group"] == row["group"] and peer["status"] in OPEN:
                        peer["status"] = "canceled"
            return True

    def close_position(self, symbol):
        position = self.get_position(symbol)
        if position is None:
            return None
        self.cancel_all_orders(symbol)
        return self.submit_order(Order(symbol=symbol, side=OrderSide.SELL, qty=position.qty))

    def get_portfolio_state(self):
        state = self.read()
        positions = {}
        for symbol, row in state["positions"].items():
            position = Position(symbol=symbol, **row)
            position.update_price(state["marks"][symbol]["price"])
            positions[symbol] = position
        return PortfolioState(cash=max(0, state["cash"] - self._reserved(state)), positions=positions,
                              equity=state["cash"] + sum(p.market_value for p in positions.values()),
                              timestamp=_time(state["health"]["as_of"]))

    @staticmethod
    def _reserved(state):
        return sum((r["order"]["qty"] - r["filled_qty"]) * r["reserve_unit"] + 0.01
                   for r in state["orders"].values() if r["status"] in OPEN and r["order"]["side"] == "buy")

    def get_position(self, symbol):
        return self.get_portfolio_state().positions.get(symbol)

    def get_all_positions(self):
        return list(self.get_portfolio_state().positions.values())

    def get_latest_prices(self, symbols):
        return TossBroker(self.client).get_latest_prices(symbols)

    def get_fills(self, since=None):
        return [FillEvent(fill_id=f["fill_id"], symbol=f["symbol"], qty=f["qty"], price=f["price"],
                          side=f["side"], ts=_time(f["at"]),
                          kind="protective" if f["protective"] else "entry")
                for f in self.read()["fills"] if since is None or f["at"] > since]

    def poll(self):
        """One observation/settlement cycle. Safe to run concurrently with an LLM turn."""
        before = self.read()
        market_open = self.is_market_open()
        profile, cost_error = None, None
        try:
            profile = self.costs.profile()
        except BrokerError as exc:
            cost_error = str(exc)
        active = {r["order"]["symbol"] for r in before["orders"].values() if r["status"] in OPEN}
        symbols = set(before["positions"]) | set(before["initial"]["positions"]) | active
        def priority(symbol):
            qty = max(before["positions"].get(symbol, {}).get("qty", 0),
                      before["initial"]["positions"].get(symbol, {}).get("qty", 0))
            return (symbol not in active, -qty * before["marks"].get(symbol, {}).get("price", 0), symbol)
        symbols = sorted(symbols, key=priority)
        books, errors, latencies = {}, {}, []
        retries = 0
        if market_open:
            def fetch(symbol):
                started = time.monotonic()
                try:
                    row = self.client.request("GET", "/api/v1/orderbook", params={"symbol": symbol})
                    books[symbol] = parse_book(row, self.clock())
                    errors.pop(symbol, None)
                except BrokerError as exc:
                    errors[symbol] = str(exc)
                latencies.append((time.monotonic() - started) * 1000)
                # Leave room under the public 15/s MARKET_DATA limit for agent reads.
                time.sleep(max(0, 0.1 - (time.monotonic() - started)))
            for symbol in symbols:
                fetch(symbol)
            # One retry per symbol, at most three reads. Never rejuvenate source time.
            for symbol in symbols:
                book = books.get(symbol)
                age = (self.clock() - _time(book["source_at"])).total_seconds() if book else None
                if symbol in errors or age is None or not 0 <= age <= before["execution"]["max_quote_age"]:
                    fetch(symbol)
                    retries += 1
                    if retries == 3:
                        break
        with self.transaction() as state:
            now = self.clock()
            # Do not use a rate that expired while fetching the orderbooks.
            if profile and now >= _time(profile["commission"]["next_check_at"]):
                try:
                    profile = self.costs.profile()
                except BrokerError as exc:
                    profile, cost_error = None, str(exc)
                now = self.clock()
            market_open = self._session_open(now)  # Fetching books may cross the session close.
            fresh = set()
            for symbol, book in books.items():
                if symbol in errors:
                    continue
                previous = state["marks"].get(symbol, {}).get("source_at")
                if previous and _time(book["source_at"]) < _time(previous):
                    errors[symbol] = "Orderbook time moved backwards"
                    continue
                age = (now - _time(book["source_at"])).total_seconds()
                if 0 <= age <= state["execution"]["max_quote_age"]:
                    fresh.add(symbol)
                bid, ask = book["bids"][0]["price"], book["asks"][0]["price"]
                state["marks"][symbol] = {"price": (bid + ask) / 2, "bid": bid, "ask": ask,
                                           "source_at": book["source_at"], "observed_at": book["observed_at"]}
            ended = now >= _time(state["end_at"])
            for row in list(state["orders"].values()):
                if row["status"] not in OPEN:
                    continue
                if ended or (not row["protective"] and
                             (row["day"] != now.astimezone(ET).date().isoformat() or not market_open)):
                    row["status"] = "expired"
                    continue
                symbol = row["order"]["symbol"]
                if profile and market_open and symbol in fresh:
                    self._match(state, row, books[symbol], profile, now)
            if profile:
                state["cost_profile"] = profile
            missing = sorted(set(symbols) - fresh) if market_open else []
            quality = quote_quality(state, now, fresh, errors) if market_open else state.get("quote_quality")
            if market_open:
                state["quote_quality"] = quality
                quality_metrics = state.setdefault("quality_metrics", {
                    "since": now.isoformat(), "polls": 0, "fresh_polls": 0,
                    "indicative_polls": 0, "unavailable_polls": 0, "retry_requests": 0,
                })
                quality_metrics["polls"] += 1
                quality_metrics[quality["status"] + "_polls"] += 1
                quality_metrics["retry_requests"] += retries
            state["health"] = {"as_of": now.isoformat(), "status": "ended" if ended else
                               ("blocked" if cost_error or (market_open and not quality["valuation_usable"]) else
                                ("degraded" if missing else "ok")),
                               "market_open": market_open, "cost_error": cost_error,
                               "missing_or_stale_books": missing, "book_errors": errors,
                               "agent_ready": not ended and market_open and not cost_error and quality["valuation_usable"],
                               "quote_retries": retries,
                               "http_ms_max": max(latencies, default=0),
                               "http_ms_mean": sum(latencies) / len(latencies) if latencies else 0}
            state["metrics"]["polls"] += 1
            if state["health"]["status"] == "blocked":
                state["metrics"]["blocked_polls"] += 1
            # Sampling every >=30s keeps multi-day reports small. Broker state and
            # each fill are committed on every poll regardless of sampling.
            last = state.get("last_snapshot_at")
            if market_open and (last is None or (now - _time(last)).total_seconds() >= 30):
                report = self._report(state)
                equity = report["equity_usd"]
                metrics = state["metrics"]
                if quality["all_quotes_fresh"]:
                    metrics["valid_snapshots"] += 1
                    metrics["peak_equity"] = max(metrics["peak_equity"], equity)
                    metrics["max_drawdown_pct"] = max(metrics["max_drawdown_pct"],
                                                      (1 - equity / metrics["peak_equity"]) * 100)
                    record_session(state, now, report)
                metrics["snapshots"] += 1
                state["last_snapshot_at"] = now.isoformat()
                self._append_snapshot({"at": now.isoformat(), "equity": equity,
                                       "hold_equity": report["hold_equity_usd"],
                                       "health": state["health"], "marks": state["marks"],
                                       "quote_quality": quality, "implementation": "F104",
                                       "fill_count": len(state["fills"])})
        return self.report()

    def _match(self, state, row, book, profile, now):
        source = _time(book["source_at"])
        ready = _time(row["ready_at"])
        if now < ready or source < ready or _time(book["observed_at"]) < ready:
            return  # No pre-order quote or pre-activation liquidity may fill an order.
        order = row["order"]
        side, symbol = order["side"], order["symbol"]
        bid = book["bids"][0]["price"]
        if order["order_type"] == "stop" and not row["triggered"]:
            if bid > order["stop_price"]:
                return
            row["triggered"] = True
            row["ready_at"] = (now + timedelta(seconds=state["execution"]["latency_seconds"])).isoformat()
            return  # Stop becomes market on the NEXT observation, including gap risk.
        usage = state["book_usage"].get(symbol)
        if usage and source < _time(usage["source_at"]):
            return
        if usage is None or usage["source_at"] != book["source_at"]:
            usage = {"source_at": book["source_at"], "buy": {}, "sell": {}}
            state["book_usage"][symbol] = usage
        remaining = order["qty"] - row["filled_qty"]
        levels = book["asks" if side == "buy" else "bids"]
        slip = state["execution"]["slippage_bps"] / 10000
        for level in levels:
            raw_price = level["price"]
            price = raw_price * (1 + slip if side == "buy" else 1 - slip)
            if order["order_type"] == "limit":
                limit = order["limit_price"]
                if (side == "buy" and price > limit) or (side == "sell" and price < limit):
                    break  # No touch-only fills or fills beyond a limit price.
            key = str(raw_price)
            available = max(0, level["volume"] * state["execution"]["participation"] - usage[side].get(key, 0))
            qty = min(remaining, available)
            if side == "sell":
                qty = min(qty, state["positions"].get(symbol, {}).get("qty", 0))
            else:
                # Include accrued order-total rounding in the cash constraint.
                rate = float(profile["commission"]["rate"])
                qty = min(qty, max(0, (state["cash"] - 0.01) / (price * (1 + rate))))
            qty = math.floor(qty) if side == "buy" else math.floor(qty * 1e6 + 1e-8) / 1e6
            if qty <= 0:
                continue
            value = qty * price
            previous = row["commission"] + row["regulatory"]
            totals = TossCosts.accrue(profile, side, value,
                                     row["commission_basis"], row["regulatory_basis"])
            fees = max(0, totals["total"] - previous)
            if side == "buy" and value + fees > state["cash"] + 1e-8:
                continue
            self._apply_fill(state, row, qty, price, value, fees, totals, book, profile, now)
            usage[side][key] = usage[side].get(key, 0) + qty
            remaining -= qty
            if remaining < 1e-8:
                break

    def _apply_fill(self, state, row, qty, price, value, fees, totals, book, profile, now):
        order = row["order"]
        symbol, side = order["symbol"], order["side"]
        old_commission, old_regulatory = row["commission"], row["regulatory"]
        if side == "buy":
            state["cash"] = round(state["cash"] - value - fees, 8)
            old = state["positions"].get(symbol, {"qty": 0, "avg_entry_price": 0})
            state["positions"][symbol] = {"qty": old["qty"] + qty,
                "avg_entry_price": (old["qty"] * old["avg_entry_price"] + value) / (old["qty"] + qty)}
        else:
            state["cash"] = round(state["cash"] + value - fees, 8)
            state["positions"][symbol]["qty"] = round(state["positions"][symbol]["qty"] - qty, 6)
            if state["positions"][symbol]["qty"] < 1e-8:
                del state["positions"][symbol]
        row["filled_qty"] += qty
        row["filled_notional"] += value
        row["commission"] = totals["commission"]
        row["regulatory"] = totals["regulatory"]
        row["commission_basis"] = totals["commission_basis"]
        row["regulatory_basis"] = totals["regulatory_basis"]
        row["filled_at"] = now.isoformat()
        row["status"] = "filled" if row["filled_qty"] >= order["qty"] - 1e-8 else "partial"
        state["fills"].append({"fill_id": uuid.uuid4().hex, "order_id": row["id"],
            "symbol": symbol, "side": side, "qty": qty, "price": price, "at": now.isoformat(),
            "commission": totals["commission"] - old_commission,
            "regulatory": totals["regulatory"] - old_regulatory,
            "cost_profile": profile, "book": book, "submitted_at": row["submitted_at"],
            "protective": row["protective"],
            "spread_cost": qty * abs((book["asks"][0]["price"] + book["bids"][0]["price"]) / 2 -
                                     (book["asks"][0]["price"] if side == "buy" else book["bids"][0]["price"])),
            "execution_shortfall": qty * (price - (book["asks"][0]["price"] + book["bids"][0]["price"]) / 2) *
                                   (1 if side == "buy" else -1)})
        if order["order_class"] == "bracket":
            self._protect(state, symbol, qty, order["stop_loss_price"], order["take_profit_price"], row["id"], now)
        if row["group"]:
            parent = state["orders"].get(row["group"])
            if parent and parent["status"] in OPEN:
                parent["status"] = "canceled"
            for peer in state["orders"].values():
                if peer["id"] != row["id"] and peer["group"] == row["group"] and peer["status"] in OPEN:
                    peer["order"]["qty"] -= qty
                    if peer["order"]["qty"] <= peer["filled_qty"] + 1e-8:
                        peer["status"] = "canceled"
        if side == "sell" and symbol not in state["positions"]:
            for peer in state["orders"].values():
                if peer["order"]["symbol"] == symbol and peer["order"]["side"] == "sell" and peer["status"] in OPEN:
                    peer["status"] = "canceled"
        elif side == "sell":
            # A manual trim leaves existing protection in place while it fills,
            # but each remaining leg must fit the actual holding, including after
            # partial fills. OCO peer reductions above preserve group quantities.
            remaining = state["positions"][symbol]["qty"]
            for peer in state["orders"].values():
                if peer["order"]["symbol"] == symbol and peer["protective"] and peer["status"] in OPEN:
                    peer["order"]["qty"] = min(peer["order"]["qty"], peer["filled_qty"] + remaining)

    def _append_snapshot(self, row):
        # Under account.lock. Mode is private even before a runner sets umask.
        import os
        fd = os.open(self.root / "equity.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            storage._check_file(stream.fileno())
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    @staticmethod
    def _report(state):
        def value(positions):
            return sum(p["qty"] * state["marks"][s]["price"] for s, p in positions.items())
        recent_fills = []
        for fill in state["fills"][-10:]:
            order = state["orders"][fill["order_id"]]["order"]
            reason = ("stop" if order["order_type"] == "stop" else "take_profit") if fill["protective"] else (
                "entry" if fill["side"] == "buy" else "exit")
            recent_fills.append({k: fill[k] for k in ("order_id", "symbol", "side", "qty", "price", "at")}
                                | {"reason": reason})
        equity = state["cash"] + value(state["positions"])
        hold = state["initial"]["cash"] + value(state["initial"]["positions"])
        initial = state["initial"]["equity"]
        fees = sum(f["commission"] + f["regulatory"] for f in state["fills"])
        shortfall = sum(f["execution_shortfall"] for f in state["fills"])
        extra_cost = sum(f["qty"] * f["price"] * 0.001 for f in state["fills"])
        return {"simulation": True, "created_at": state["created_at"], "end_at": state["end_at"],
                "equity_usd": equity, "hold_equity_usd": hold, "initial_equity_usd": initial,
                "cash_usd": state["cash"], "reserved_cash_usd": TossShadowBroker._reserved(state),
                "net_return_pct": (equity / initial - 1) * 100,
                "hold_return_pct": (hold / initial - 1) * 100,
                "excess_return_pct_points": (equity - hold) / initial * 100,
                "fees_usd": fees, "execution_shortfall_usd": shortfall,
                "stress_extra_10bps_each_fill_usd": extra_cost,
                "stress_net_return_pct": ((equity - extra_cost) / initial - 1) * 100,
                "fill_count": len(state["fills"]),
                "recent_fills": recent_fills,
                "open_order_count": sum(r["status"] in OPEN for r in state["orders"].values()),
                "agent_turn_count": len(state["turns"]),
                "agent_error_count": sum(t["status"] == "error" for t in state["turns"]),
                "runner_stopped_at": state.get("runner_stopped_at"), "metrics": state["metrics"],
                "agent_config": state.get("agent_config"), "runner": state.get("runner"),
                "health": state["health"], "execution": state["execution"],
                "quote_quality": state.get("quote_quality"),
                "quality_metrics": state.get("quality_metrics"),
                "session_performance": state.get("session_performance", {}),
                "runtime_revisions": state.get("runtime_revisions", []),
                "execution_retries": state.get("execution_retries", {}),
                "cost_profile": state["cost_profile"], "assumptions": state["assumptions"],
                "return_basis": "marked equity after simulated incurred costs; open positions not liquidated",
                "stress_note": "Cost sensitivity only; no claim of replaying alternative latency/fill paths"}

    def report(self):
        return self._report(self.read())

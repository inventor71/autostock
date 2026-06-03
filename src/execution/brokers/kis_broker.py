"""KIS (한국투자증권) Korean-equity broker over the 모의/실전 REST domain.

Capability by environment (verified 2026-06-03): KIS **모의투자 does not support
stop-limit orders** (ORD_DVSN=22 → "모의투자에서 제공하지 않는 주문유형"), while 실전
does. So the take-profit leg is always a real resting LIMIT sell (both domains
serve it), but the stop-loss leg differs — placed via the abstract ``_arm_stop``
hook: ``KisPaperBroker`` registers a *polled* stop (the executor's
``run_polled_exits`` covers it, since ``protected_symbols`` keys on a STOP leg);
a future ``KisLiveBroker`` will place an exchange stop (ORD_DVSN=22 + CNDT_PRIC).

OcoGroup membership is journalled (workspace/kis_oco_groups.json) so a daemon
restart can re-bind the resting legs (OpenOrder carries no group id).
"""

from __future__ import annotations

import json
import time
from abc import abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from loguru import logger

from src.agent.intraday.records import FillEvent
from src.core.exceptions import BrokerError
from src.core.models import FilledOrder, OpenOrder, Order, PortfolioState, Position
from src.core.types import OrderClass, OrderSide, OrderType
from src.execution.base import BaseBroker
from src.execution.brokers.kis_pricing import floor_qty, round_to_tick
from src.execution.brokers.kis_rest import KisRestClient

_KST = ZoneInfo("Asia/Seoul")
_ORDER_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
_CANCEL_PATH = "/uapi/domestic-stock/v1/trading/order-rvsecncl"
_BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
_OPENORD_PATH = "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
_CCLD_PATH = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"

# ORD_DVSN
_DVSN_LIMIT = "00"
_DVSN_MARKET = "01"


def _f(d: dict, *keys: str, default: float = 0.0) -> float:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return default


@dataclass
class OcoGroup:
    """An emulated OCO pair: a resting take-profit LIMIT + a stop-loss leg.

    In 모의 the stop is polled (``sl_odno`` empty, ``stop_price`` set); in 실전 it
    is an exchange order (``sl_odno`` set). Filling/exiting one leg cancels the other.
    """

    group_id: str
    symbol: str
    qty: int
    entry_odno: str | None = None
    tp_odno: str | None = None
    sl_odno: str | None = None
    tp_price: float = 0.0
    stop_price: float = 0.0
    state: str = "ARMED"  # PENDING_ENTRY | ARMED | RESOLVED


class _OcoStore:
    """Write-through JSON journal of OcoGroups (survives daemon restart)."""

    def __init__(self, path: Path):
        self._path = path
        self.groups: dict[str, OcoGroup] = {}
        self._counter = 0
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text())
            for g in raw.get("groups", []):
                self.groups[g["group_id"]] = OcoGroup(**g)
            self._counter = raw.get("counter", len(self.groups))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"KIS OCO journal load failed ({e}); starting empty")

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(
            {"counter": self._counter, "groups": [asdict(g) for g in self.groups.values()]},
            ensure_ascii=False, indent=2,
        ))
        tmp.replace(self._path)

    def new_group(self, symbol: str, qty: int) -> OcoGroup:
        self._counter += 1
        g = OcoGroup(group_id=f"oco_{self._counter}", symbol=symbol, qty=qty)
        self.groups[g.group_id] = g
        return g

    def resolve(self, group_id: str) -> None:
        if group_id in self.groups:
            self.groups[group_id].state = "RESOLVED"
            del self.groups[group_id]


class KisBroker(BaseBroker):
    """Common KIS REST broker. Abstract on the stop-loss mechanism (``_arm_stop``)."""

    halt_reference_symbol = "069500"  # KODEX 200 — KR circuit-breaker benchmark
    cancel_settle_wait = 0.0  # KIS cancel is synchronous; no settle-poll needed
    # KST trading calendar — AgentTradingMode schedules research/open/close from this
    # (brokers without it fall back to US/Eastern defaults).
    market_schedule = {
        "timezone": "Asia/Seoul",
        "research": (8, 0), "open": (9, 0), "close": (15, 20),
    }

    def __init__(
        self,
        appkey: str,
        appsecret: str,
        account: str,
        *,
        paper: bool = True,
        connect_timeout: float = 3.0,
        read_timeout: float = 5.0,
        rate_limit_per_sec: float = 2.0,
        oco_journal: str | Path = "workspace/kis_oco_groups.json",
        fill_poll_timeout: float = 3.0,
    ):
        self.paper = paper
        self._c = KisRestClient(
            appkey, appsecret, paper=paper,
            connect_timeout=connect_timeout, read_timeout=read_timeout,
            rate_limit_per_sec=rate_limit_per_sec,
        )
        cano, _, prdt = account.partition("-")
        self._cano = cano
        self._prdt = prdt or "01"
        self._oco = _OcoStore(Path(oco_journal))
        self._fill_poll_timeout = fill_poll_timeout

    @property
    def client(self) -> KisRestClient:
        """Shared transport — reused by KisDataProvider so both honour one token."""
        return self._c

    # -- tr_id helpers (env-aware) -------------------------------------- #
    def _tr(self, real: str, demo: str) -> str:
        return demo if self.paper else real

    # -- normalization -------------------------------------------------- #
    @staticmethod
    def _pdno(symbol: str) -> str:
        return symbol.strip().upper()

    def _order_body(self, side: OrderSide, pdno: str, qty: int, dvsn: str,
                    unpr: int, cndt: str = "") -> dict:
        return {
            "CANO": self._cano, "ACNT_PRDT_CD": self._prdt, "PDNO": pdno,
            "ORD_DVSN": dvsn, "ORD_QTY": str(qty), "ORD_UNPR": str(unpr),
            "EXCG_ID_DVSN_CD": "KRX", "SLL_TYPE": "" if side is OrderSide.BUY else "01",
            "CNDT_PRIC": cndt,
        }

    def _raw_order(self, side: OrderSide, pdno: str, qty: int, dvsn: str,
                   unpr: int, cndt: str = "") -> tuple[str, str]:
        """Place one order-cash order; return (odno, krx_org). Raise on rejection."""
        tr = self._tr("TTTC0011U" if side is OrderSide.SELL else "TTTC0012U",
                      "VTTC0011U" if side is OrderSide.SELL else "VTTC0012U")
        res = self._c.post(_ORDER_PATH, tr, self._order_body(side, pdno, qty, dvsn, unpr, cndt))
        if res.get("rt_cd") != "0":
            raise BrokerError(f"KIS order rejected [{res.get('msg_cd')}]: {res.get('msg1')}")
        out = res.get("output") or {}
        return out.get("ODNO", ""), out.get("KRX_FWDG_ORD_ORGNO", "")

    # -- order entry ---------------------------------------------------- #
    def submit_order(self, order: Order) -> FilledOrder:
        pdno = self._pdno(order.symbol)
        qty = floor_qty(order.qty)
        if qty < 1:
            raise BrokerError(f"KIS: order qty floors to {qty} (<1) for {pdno}")

        if order.order_class in (OrderClass.BRACKET, OrderClass.OCO):
            return self._submit_bracket(order, pdno, qty)
        if order.order_type is OrderType.TRAILING_STOP:
            raise BrokerError("KIS: trailing_stop is not supported")
        if order.order_type is OrderType.STOP:
            # Plain protective stop — routed through the env-specific hook.
            group = self._oco.new_group(pdno, qty)
            group.entry_odno = None
            self._arm_stop(group, order.side, round_to_tick(order.stop_price or 0), qty)
            self._oco.save()
            return self._pending(pdno, order.side, qty)

        if order.order_type is OrderType.MARKET:
            odno, _ = self._raw_order(order.side, pdno, qty, _DVSN_MARKET, 0)
        else:  # LIMIT
            unpr = round_to_tick(order.limit_price or 0)
            odno, _ = self._raw_order(order.side, pdno, qty, _DVSN_LIMIT, unpr)
        return self._confirm_fill(odno, pdno, order.side, qty)

    def _submit_bracket(self, order: Order, pdno: str, qty: int) -> FilledOrder:
        group = self._oco.new_group(pdno, qty)
        group.tp_price = float(round_to_tick(order.take_profit_price or 0))
        group.stop_price = float(round_to_tick(order.stop_loss_price or 0))

        if order.order_class is OrderClass.BRACKET:
            # Place the entry; DEFER the take-profit/stop arming to reconcile, once
            # the *actual* filled position is observed. This sizes the TP to the real
            # fill (not the requested qty — KIS fills can be partial/lagging) and
            # avoids a 5s-reconcile cancelling a TP placed before the balance reflects
            # the entry (F30 critic HIGH-1/HIGH-3). The journalled stop_price is honced
            # honoured by the polled exit from when the group exists (get_protective_stops).
            if order.order_type is OrderType.MARKET:
                entry_odno, _ = self._raw_order(order.side, pdno, qty, _DVSN_MARKET, 0)
            else:
                entry_odno, _ = self._raw_order(order.side, pdno, qty, _DVSN_LIMIT,
                                                round_to_tick(order.limit_price or 0))
            group.entry_odno = entry_odno
            group.state = "PENDING_ENTRY"
            self._oco.save()
            return self._confirm_fill(entry_odno, pdno, order.side, qty)

        # OCO on an existing position: arm immediately against the held qty.
        self._arm_group(group, qty)
        self._oco.save()
        return self._pending(pdno, OrderSide.SELL, qty)

    def _arm_group(self, group: OcoGroup, qty: int) -> None:
        """Place the resting take-profit LIMIT + the (env-specific) stop-loss leg."""
        if not group.tp_odno and group.tp_price > 0:
            tp_odno, _ = self._raw_order(
                OrderSide.SELL, group.symbol, qty, _DVSN_LIMIT, int(group.tp_price))
            group.tp_odno = tp_odno
        group.qty = qty
        self._arm_stop(group, OrderSide.SELL, int(group.stop_price), qty)
        group.state = "ARMED"

    @abstractmethod
    def _arm_stop(self, group: OcoGroup, side: OrderSide, stop_price: int, qty: int) -> None:
        """Place/record the stop-loss leg. 모의: polled (no exchange order); 실전:
        exchange stop-limit (ORD_DVSN=22 + CNDT_PRIC). Must set group.stop_price and,
        for an exchange stop, group.sl_odno."""

    # -- fills ---------------------------------------------------------- #
    def _confirm_fill(self, odno: str, pdno: str, side: OrderSide, qty: int) -> FilledOrder:
        """Briefly poll order status to confirm a fill; fall back to pending."""
        deadline = time.monotonic() + self._fill_poll_timeout
        while time.monotonic() < deadline:
            st = self.get_order_status(odno)
            if st and st.qty > 0:
                return st
            time.sleep(0.5)
        return self._pending(pdno, side, qty, order_id=odno)

    @staticmethod
    def _pending(pdno: str, side: OrderSide, qty: int, order_id: str = "") -> FilledOrder:
        return FilledOrder(order_id=order_id, symbol=pdno, side=side, qty=0.0,
                           filled_price=0.0, filled_at=datetime.now(_KST))

    # -- queries -------------------------------------------------------- #
    def _balance(self) -> tuple[list[dict], dict]:
        params = {
            "CANO": self._cano, "ACNT_PRDT_CD": self._prdt, "AFHR_FLPR_YN": "N",
            "OFL_YN": "", "INQR_DVSN": "02", "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
        }
        res = self._c.get(_BALANCE_PATH, self._tr("TTTC8434R", "VTTC8434R"), params)
        if res.get("rt_cd") != "0":
            raise BrokerError(f"KIS balance inquiry failed [{res.get('msg_cd')}]: {res.get('msg1')}")
        out1 = res.get("output1") or []
        out2 = (res.get("output2") or [{}])
        return out1, (out2[0] if out2 else {})

    @staticmethod
    def _to_position(row: dict) -> Position | None:
        qty = _f(row, "hldg_qty")
        if qty <= 0:
            return None
        return Position(
            symbol=row.get("pdno", ""), qty=qty,
            avg_entry_price=_f(row, "pchs_avg_pric"),
            current_price=_f(row, "prpr"),
        )

    def get_all_positions(self) -> list[Position]:
        out1, _ = self._balance()
        return [p for row in out1 if (p := self._to_position(row))]

    def get_position(self, symbol: str) -> Position | None:
        pdno = self._pdno(symbol)
        for p in self.get_all_positions():
            if p.symbol.upper() == pdno:
                return p
        return None

    def get_portfolio_state(self) -> PortfolioState:
        out1, summary = self._balance()
        positions = {p.symbol: p for row in out1 if (p := self._to_position(row))}
        cash = _f(summary, "dnca_tot_amt", "prvs_rcdl_excc_amt")
        equity = _f(summary, "tot_evlu_amt", "nass_amt", default=cash)
        return PortfolioState(cash=cash, equity=equity, positions=positions)

    def get_open_orders(self, symbol: str | None = None) -> list[OpenOrder]:
        params = {
            "CANO": self._cano, "ACNT_PRDT_CD": self._prdt, "INQR_DVSN_1": "0",
            "INQR_DVSN_2": "0", "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
        }
        try:
            res = self._c.get(_OPENORD_PATH, self._tr("TTTC0084R", "VTTC0084R"), params)
        except BrokerError:
            return []
        if res.get("rt_cd") != "0":
            return []
        pdno_filter = self._pdno(symbol) if symbol else None
        orders: list[OpenOrder] = []
        for row in res.get("output") or []:
            pdno = row.get("pdno", "")
            if pdno_filter and pdno.upper() != pdno_filter:
                continue
            remaining = _f(row, "ordng_qty", "ord_qty") - _f(row, "tot_ccld_qty")
            if remaining <= 0:
                continue
            side = OrderSide.SELL if row.get("sll_buy_dvsn_cd") == "01" else OrderSide.BUY
            orders.append(OpenOrder(
                order_id=row.get("odno", ""), symbol=pdno, side=side,
                order_type=OrderType.LIMIT, qty=remaining,
                limit_price=_f(row, "ord_unpr") or None,
            ))
        return orders

    def get_order_status(self, order_id: str) -> FilledOrder | None:
        """Today's fill state for an order via inquire-daily-ccld. Returns a
        FilledOrder with the executed qty/avg price, or None if unfilled/unknown."""
        today = datetime.now(_KST).strftime("%Y%m%d")
        params = {
            "CANO": self._cano, "ACNT_PRDT_CD": self._prdt,
            "INQR_STRT_DT": today, "INQR_END_DT": today, "SLL_BUY_DVSN_CD": "00",
            "PDNO": "", "CCLD_DVSN": "00", "INQR_DVSN": "00", "INQR_DVSN_3": "00",
            "ORD_GNO_BRNO": "", "ODNO": order_id, "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
        }
        try:
            res = self._c.get(_CCLD_PATH, self._tr("TTTC0081R", "VTTC0081R"), params)
        except BrokerError:
            return None
        if res.get("rt_cd") != "0":
            return None
        for row in res.get("output1") or []:
            if row.get("odno") != order_id:
                continue
            ccld = _f(row, "tot_ccld_qty")
            if ccld <= 0:
                return None  # accepted but not yet filled
            avg = _f(row, "avg_prvs")
            if avg <= 0:
                avg = _f(row, "tot_ccld_amt") / ccld if ccld else 0.0
            return FilledOrder(
                order_id=order_id, symbol=row.get("pdno", ""),
                side=OrderSide.SELL if row.get("sll_buy_dvsn_cd") == "01" else OrderSide.BUY,
                qty=ccld, filled_price=avg, filled_at=datetime.now(_KST))
        return None

    def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        prices: dict[str, float] = {}
        for sym in symbols:
            try:
                res = self._c.get(_PRICE_PATH, "FHKST01010100",
                                  {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": self._pdno(sym)})
                px = _f(res.get("output") or {}, "stck_prpr")
                if px > 0:
                    prices[sym] = px
            except BrokerError:
                continue
        return prices

    # -- mutations ------------------------------------------------------ #
    def cancel_order(self, order_id: str) -> bool:
        org = ""
        for row in self._open_rows():
            if row.get("odno") == order_id:
                org = row.get("ord_gno_brno", "") or row.get("KRX_FWDG_ORD_ORGNO", "")
                break
        body = {
            "CANO": self._cano, "ACNT_PRDT_CD": self._prdt,
            "KRX_FWDG_ORD_ORGNO": org, "ORGN_ODNO": order_id, "ORD_DVSN": _DVSN_LIMIT,
            "RVSE_CNCL_DVSN_CD": "02", "ORD_QTY": "0", "ORD_UNPR": "0", "QTY_ALL_ORD_YN": "Y",
        }
        res = self._c.post(_CANCEL_PATH, self._tr("TTTC0013U", "VTTC0013U"), body)
        return res.get("rt_cd") == "0"

    def _open_rows(self) -> list[dict]:
        params = {
            "CANO": self._cano, "ACNT_PRDT_CD": self._prdt, "INQR_DVSN_1": "0",
            "INQR_DVSN_2": "0", "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
        }
        try:
            res = self._c.get(_OPENORD_PATH, self._tr("TTTC0084R", "VTTC0084R"), params)
            return res.get("output") or [] if res.get("rt_cd") == "0" else []
        except BrokerError:
            return []

    def close_position(self, symbol: str) -> FilledOrder | None:
        pos = self.get_position(symbol)
        if pos is None or pos.qty <= 0:
            return None
        pdno = self._pdno(symbol)
        odno, _ = self._raw_order(OrderSide.SELL, pdno, int(pos.qty), _DVSN_MARKET, 0)
        # Drop any OCO group on this symbol (its legs are now obsolete).
        for gid in [g.group_id for g in self._oco.groups.values() if g.symbol == pdno]:
            self._cancel_group_legs(self._oco.groups[gid])
            self._oco.resolve(gid)
        self._oco.save()
        return self._confirm_fill(odno, pdno, OrderSide.SELL, int(pos.qty))

    # -- OCO reconcile -------------------------------------------------- #
    def reconcile_oco(self) -> None:
        """Drive the OCO state machine:
        - PENDING_ENTRY: once the entry fills (position observed), arm TP/SL sized
          to the real held qty → ARMED. If the entry order is gone with no position
          (rejected/cancelled), resolve.
        - ARMED: once the position exits (TP filled or polled stop sold), cancel the
          dangling leg and resolve.
        """
        if not self._oco.groups:
            return
        held = {p.symbol.upper(): p.qty for p in self.get_all_positions()}
        open_odnos = {o.order_id for o in self.get_open_orders()}
        for gid in list(self._oco.groups):
            g = self._oco.groups[gid]
            h = held.get(g.symbol.upper(), 0)
            if g.state == "PENDING_ENTRY":
                if h > 0:
                    self._arm_group(g, int(h))  # entry (partly) filled → arm TP/SL
                elif g.entry_odno and g.entry_odno not in open_odnos:
                    self._oco.resolve(gid)  # entry gone, no position → rejected
                # else: entry still resting — wait
            elif g.state == "ARMED" and h <= 0:
                self._cancel_group_legs(g)
                self._oco.resolve(gid)
        self._oco.save()

    def get_protective_stops(self) -> dict[str, float]:
        """Per-symbol stop levels for the polled exit. 모의 has no exchange stop,
        so run_polled_exits enforces the agent's journalled stop at this price
        (not the flat risk.stop_loss_pct) — see RiskManager.check_stop_loss."""
        return {
            g.symbol.upper(): g.stop_price
            for g in self._oco.groups.values()
            if g.stop_price > 0 and g.state in ("PENDING_ENTRY", "ARMED")
        }

    def _cancel_group_legs(self, g: OcoGroup) -> None:
        for odno in (g.tp_odno, g.sl_odno):
            if odno:
                try:
                    self.cancel_order(odno)
                except BrokerError:
                    pass

    # -- market hours --------------------------------------------------- #
    def is_market_open(self) -> bool:
        """KST regular session 09:00–15:30, Mon–Fri. Fail-closed on error."""
        try:
            now = datetime.now(_KST)
            if now.weekday() >= 5:
                return False
            minutes = now.hour * 60 + now.minute
            return 9 * 60 <= minutes <= 15 * 60 + 30
        except Exception:  # noqa: BLE001
            return False


class KisPaperBroker(KisBroker):
    """모의투자 KIS broker. The stop-loss is polled (모의 has no exchange stop)."""

    def _arm_stop(self, group: OcoGroup, side: OrderSide, stop_price: int, qty: int) -> None:
        # No exchange stop in 모의 — record the level so reconcile/run_polled_exits
        # (protected_symbols keys on a STOP leg, which we deliberately do NOT rest)
        # provide the stop. sl_odno stays empty.
        group.stop_price = float(stop_price)
        group.sl_odno = None

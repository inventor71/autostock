from __future__ import annotations

from typing import Any

from loguru import logger
from pydantic import BaseModel

from src.core.exceptions import RiskLimitError
from src.core.models import Order, PortfolioState, TradeSignal
from src.core.types import OrderClass, OrderSide, OrderType, PositionSide, Signal
from src.risk.position_sizer import PositionSizer


def _pos_float(value: Any) -> float | None:
    """Coerce an LLM-supplied level to a positive float, else None."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


# F9: structured outcome of the human-order gate (FR-6). Carries a machine
# reason_code + human message and, when computable, a pass-able suggestion
# (e.g. {"qty": 37} or {"force": True}) the console AI can offer as a retry.
class OrderDecision(BaseModel):
    accepted: bool
    order: Order | None = None
    reason_code: str = ""
    message: str = ""
    suggestion: dict[str, Any] | None = None


# Capability scope wired in F9 v1 (Q4=A). Anything outside is a fail-closed
# reject (not overridable by ``force``) — never a silent downgrade.
_SUPPORTED_TIF = frozenset({"day", "gtc", "ioc", "fok"})
_SUPPORTED_CLASS = frozenset({OrderClass.SIMPLE, OrderClass.BRACKET, OrderClass.OCO})


class RiskManager:
    """Manages risk by validating orders and enforcing limits.

    When ``use_bracket_orders`` is enabled, a BUY whose signal carries levels
    (``signal.metadata["key_levels"]`` with entry/stop_loss/take_profit, plus an
    optional absolute ``signal.metadata["atr"]``) becomes a resting BRACKET
    order: a guardrailed stop, a take-profit (LLM's or derived from
    ``default_risk_reward``), and a size derived from the *actual* stop distance
    (so per-trade risk is capped at ``max_portfolio_risk`` instead of being
    computed against a fixed assumed stop).

    It is **disabled by default**: the strategy path (TradingEngine) uses the
    legacy market-order + polled-stop behavior, while the agent path enables it.
    The agent path also supplies ``protected_symbols`` to the stop/take checks so
    a resting bracket and the polled backup never double-exit the same position.
    """

    def __init__(
        self,
        max_position_pct: float = 0.1,
        max_portfolio_risk: float = 0.02,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.15,
        max_open_positions: int = 10,
        max_stop_distance_pct: float = 0.12,
        atr_stop_multiple: float = 3.0,
        market_halt_threshold_pct: float = -0.03,
        default_risk_reward: float = 2.5,
        use_bracket_orders: bool = False,
        # F54: short-specific config (all optional). None → fall back to the
        # matching long parameter, so a deployment that doesn't set them behaves
        # exactly as before for shorts (Q3=C: shared + override).
        short_market_halt_threshold_pct: float = 0.03,
        short_stop_loss_pct: float | None = None,
        short_take_profit_pct: float | None = None,
        short_max_stop_distance_pct: float | None = None,
        individual_stock_halt_pct: float = 0.10,
    ):
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_open_positions = max_open_positions
        self.max_stop_distance_pct = max_stop_distance_pct
        self.atr_stop_multiple = atr_stop_multiple
        self.market_halt_threshold_pct = market_halt_threshold_pct
        self.default_risk_reward = default_risk_reward
        self.use_bracket_orders = use_bracket_orders
        # F54 short config (override-or-fallback resolved via the properties below).
        self.short_market_halt_threshold_pct = short_market_halt_threshold_pct
        self._short_stop_loss_pct = short_stop_loss_pct
        self._short_take_profit_pct = short_take_profit_pct
        self._short_max_stop_distance_pct = short_max_stop_distance_pct
        self.individual_stock_halt_pct = individual_stock_halt_pct
        self._new_buys_halted = False
        self._new_shorts_halted = False
        self.position_sizer = PositionSizer(
            max_position_pct=max_position_pct,
            max_portfolio_risk=max_portfolio_risk,
        )

    # F54: short parameters fall back to their long counterpart when unset.
    @property
    def short_stop_loss_pct(self) -> float:
        return (
            self._short_stop_loss_pct
            if self._short_stop_loss_pct is not None
            else self.stop_loss_pct
        )

    @property
    def short_take_profit_pct(self) -> float:
        return (
            self._short_take_profit_pct
            if self._short_take_profit_pct is not None
            else self.take_profit_pct
        )

    @property
    def short_max_stop_distance_pct(self) -> float:
        return (
            self._short_max_stop_distance_pct
            if self._short_max_stop_distance_pct is not None
            else self.max_stop_distance_pct
        )

    # ------------------------------------------------------------------ #
    # Circuit breaker
    # ------------------------------------------------------------------ #
    def update_market_halt(self, spy_change_pct: float | None) -> None:
        """Update both circuit breakers from SPY's day-change.

        A sharp drop halts new BUYS (a falling market is a bad time to add
        longs); a sharp rally halts new SHORTS (a ripping market is a bad time
        to add shorts — squeeze risk). The two breakers are independent (FR-5,
        Q4=B): a down day stops longs but leaves shorting open, and vice versa.
        The caller (engine/orchestrator) supplies SPY's day-change each cycle;
        RiskManager stays free of data access."""
        buys_halted = (
            spy_change_pct is not None
            and spy_change_pct <= self.market_halt_threshold_pct
        )
        if buys_halted and not self._new_buys_halted:
            logger.warning(
                f"Circuit breaker tripped: halting new buys "
                f"(market {spy_change_pct:.2%} <= {self.market_halt_threshold_pct:.2%})"
            )
        elif self._new_buys_halted and not buys_halted:
            logger.info("Circuit breaker cleared: new buys re-enabled")
        self._new_buys_halted = buys_halted

        shorts_halted = (
            spy_change_pct is not None
            and spy_change_pct >= self.short_market_halt_threshold_pct
        )
        if shorts_halted and not self._new_shorts_halted:
            logger.warning(
                f"Circuit breaker tripped: halting new shorts "
                f"(market {spy_change_pct:.2%} >= {self.short_market_halt_threshold_pct:.2%})"
            )
        elif self._new_shorts_halted and not shorts_halted:
            logger.info("Circuit breaker cleared: new shorts re-enabled")
        self._new_shorts_halted = shorts_halted

    @property
    def new_buys_halted(self) -> bool:
        return self._new_buys_halted

    @property
    def new_shorts_halted(self) -> bool:
        return self._new_shorts_halted

    # ------------------------------------------------------------------ #
    # Signal -> order
    # ------------------------------------------------------------------ #
    def evaluate_signal(
        self,
        signal: TradeSignal,
        price: float,
        portfolio: PortfolioState,
    ) -> Order | None:
        """Convert a trade signal to an order after risk checks.

        Returns None if the signal should be skipped.
        Raises RiskLimitError if a risk limit is violated.
        """
        if signal.signal == Signal.HOLD:
            return None

        if signal.signal == Signal.BUY:
            return self._handle_buy(signal, price, portfolio)
        if signal.signal == Signal.SELL_SHORT:
            return self._handle_sell_short(signal, price, portfolio)
        if signal.signal == Signal.BUY_TO_COVER:
            return self._handle_buy_to_cover(signal, price, portfolio)
        if signal.signal == Signal.SELL:
            return self._handle_sell(signal, price, portfolio)
        # Fail-closed: an unknown signal never silently becomes an order.
        logger.warning(f"Unknown signal {signal.signal!r} for {signal.symbol}; skipping")
        return None

    def _handle_buy(
        self,
        signal: TradeSignal,
        price: float,
        portfolio: PortfolioState,
    ) -> Order | None:
        if self._new_buys_halted:
            logger.warning(f"New buys halted (circuit breaker), skipping {signal.symbol}")
            return None

        # Check max positions
        if portfolio.position_count >= self.max_open_positions:
            logger.warning(
                f"Max positions ({self.max_open_positions}) reached, skipping {signal.symbol}"
            )
            return None

        # Don't add to existing position
        if signal.symbol in portfolio.positions:
            logger.debug(f"Already holding {signal.symbol}, skipping buy")
            return None

        if self.use_bracket_orders:
            bracket = self._build_bracket_buy(signal, price, portfolio)
            if bracket is not None:
                return bracket
            # No usable stop level -> fall through to a plain market buy whose
            # stop is handled by the polled backup (check_stop_loss).

        return self._simple_buy(signal, price, portfolio)

    def _build_bracket_buy(
        self,
        signal: TradeSignal,
        price: float,
        portfolio: PortfolioState,
    ) -> Order | None:
        """Build a resting BRACKET order from the signal's levels, or None if
        there is no stop source to anchor it (caller then does a simple buy)."""
        levels = signal.metadata.get("key_levels") or {}
        entry = _pos_float(levels.get("entry"))
        stop = _pos_float(levels.get("stop_loss"))
        target = _pos_float(levels.get("take_profit"))
        atr = _pos_float(signal.metadata.get("atr"))  # absolute $ per share

        entry_ref = entry if entry is not None else price
        if entry_ref <= 0:
            return None

        resolved_stop = self._resolve_stop(entry_ref, stop, atr)
        if resolved_stop is None:
            return None

        # Size from the *actual* stop distance: risk per trade is capped at
        # max_portfolio_risk regardless of how wide/tight the stop is.
        stop_frac = (entry_ref - resolved_stop) / entry_ref
        shares = self.position_sizer.calculate_shares(
            symbol=signal.symbol,
            price=entry_ref,
            portfolio=portfolio,
            stop_loss_pct=stop_frac,
            confidence=signal.confidence,
        )
        if shares <= 0:
            logger.debug(f"Bracket size is 0 for {signal.symbol}")
            return None

        if target is not None and target > entry_ref:
            resolved_target = target
        else:
            resolved_target = entry_ref + self.default_risk_reward * (entry_ref - resolved_stop)

        # A target entry below the current price rests as a LIMIT (buy the dip);
        # otherwise enter at market now.
        use_limit = entry is not None and entry < price

        logger.info(
            f"Risk approved: BRACKET BUY {shares} {signal.symbol} "
            f"entry~{entry_ref:.2f} stop={resolved_stop:.2f} target={resolved_target:.2f} "
            f"(confidence={signal.confidence:.2f})"
        )
        return Order(
            symbol=signal.symbol,
            side=OrderSide.BUY,
            qty=float(shares),
            order_type=OrderType.LIMIT if use_limit else OrderType.MARKET,
            limit_price=round(entry_ref, 2) if use_limit else None,
            order_class=OrderClass.BRACKET,
            take_profit_price=round(resolved_target, 2),
            stop_loss_price=round(resolved_stop, 2),
            time_in_force="gtc",
        )

    def _resolve_stop(
        self, entry: float, stop: float | None, atr: float | None
    ) -> float | None:
        """Resolve a long stop price: explicit level, else ATR-based, else None.

        The stop is clamped so it is never further than ``max_stop_distance_pct``
        below entry (caps the per-trade loss); tighter stops are kept as-is.
        """
        if stop is not None and stop < entry:
            resolved = stop
        elif atr is not None:
            resolved = entry - self.atr_stop_multiple * atr
        else:
            return None

        floor_stop = entry * (1 - self.max_stop_distance_pct)
        if resolved < floor_stop:
            resolved = floor_stop
        if resolved >= entry:
            return None
        return resolved

    def _simple_buy(
        self,
        signal: TradeSignal,
        price: float,
        portfolio: PortfolioState,
    ) -> Order | None:
        shares = self.position_sizer.calculate_shares(
            symbol=signal.symbol,
            price=price,
            portfolio=portfolio,
            stop_loss_pct=self.stop_loss_pct,
            confidence=signal.confidence,
        )

        if shares <= 0:
            logger.debug(f"Position size is 0 for {signal.symbol}")
            return None

        logger.info(
            f"Risk approved: BUY {shares} {signal.symbol} @ ~{price:.2f} "
            f"(confidence={signal.confidence:.2f})"
        )

        return Order(
            symbol=signal.symbol,
            side=OrderSide.BUY,
            qty=float(shares),
        )

    def _handle_sell(
        self,
        signal: TradeSignal,
        price: float,
        portfolio: PortfolioState,
    ) -> Order | None:
        position = portfolio.positions.get(signal.symbol)
        if position is None:
            logger.debug(f"No position for {signal.symbol}, skipping sell")
            return None

        # Support partial sell
        sell_pct = getattr(signal, "sell_pct", 1.0)
        sell_pct = max(0.0, min(1.0, sell_pct))  # Clamp to 0-1 range

        # Sell the requested fraction of the ACTUAL position. A full exit sells
        # the exact held quantity -- never truncate to int, which broke fractional
        # positions (int(0.5)=0 then forced a 1-share oversell) and was
        # inconsistent with the stop/take-profit exits that sell position.qty as a
        # float. Fractional sizing is kept so Alpaca fractional shares exit cleanly.
        qty = min(round(position.qty * sell_pct, 9), position.qty)
        if qty <= 0:
            logger.debug(
                f"Sell quantity rounds to 0 for {signal.symbol} "
                f"(sell_pct={sell_pct:.2f}), skipping"
            )
            return None

        logger.info(
            f"Risk approved: SELL {qty} {signal.symbol} @ ~{price:.2f} "
            f"({sell_pct:.0%} of {position.qty} shares)"
        )

        return Order(
            symbol=signal.symbol,
            side=OrderSide.SELL,
            qty=qty,
        )

    # ------------------------------------------------------------------ #
    # F54: short entry / cover (mirror of buy / sell with inverted geometry)
    # ------------------------------------------------------------------ #
    def _handle_sell_short(
        self,
        signal: TradeSignal,
        price: float,
        portfolio: PortfolioState,
    ) -> Order | None:
        """Open a short. Unlike a long, a short has no fallback to an
        unprotected market order — a short with no resolvable stop is REJECTED
        (FR-4.1: mandatory stop, because a short's loss is unbounded)."""
        if self._new_shorts_halted:
            logger.warning(f"New shorts halted (circuit breaker), skipping {signal.symbol}")
            return None

        if portfolio.position_count >= self.max_open_positions:
            logger.warning(
                f"Max positions ({self.max_open_positions}) reached, skipping short {signal.symbol}"
            )
            return None

        # Same-direction guard. A LONG held here means the executor must flip
        # (close long → then short); RiskManager evaluates one signal only, so it
        # declines and lets the executor sequence the flip (BR-6/BR-9).
        existing = portfolio.positions.get(signal.symbol)
        if existing is not None:
            if existing.side == PositionSide.SHORT:
                logger.debug(f"Already short {signal.symbol}, skipping")
            else:
                logger.debug(
                    f"Holding long {signal.symbol}; short entry deferred to executor flip"
                )
            return None

        # Individual-stock squeeze guard: don't open a fresh short into a name
        # that is already ripping today (FR-5.4). prev_close comes from the
        # signal metadata when the caller has it; absent → guard is skipped.
        prev_close = _pos_float(signal.metadata.get("prev_close"))
        if prev_close is not None and price > 0:
            day_change = (price - prev_close) / prev_close
            if day_change >= self.individual_stock_halt_pct:
                logger.warning(
                    f"Short rejected for {signal.symbol}: up {day_change:.1%} today "
                    f">= {self.individual_stock_halt_pct:.1%} (squeeze guard)"
                )
                return None

        bracket = self._build_bracket_short(signal, price, portfolio)
        if bracket is not None:
            return bracket
        # No resolvable stop → reject (mandatory stop). This is the key
        # divergence from _handle_buy, which falls through to a plain market buy.
        logger.warning(
            f"Short entry for {signal.symbol} requires a stop (explicit level or "
            f"ATR); none resolvable — rejecting (fail-closed)"
        )
        return None

    def _build_bracket_short(
        self,
        signal: TradeSignal,
        price: float,
        portfolio: PortfolioState,
    ) -> Order | None:
        """Build a resting short BRACKET from the signal's levels, or None if
        there is no stop source to anchor it. Inverted geometry vs a long: the
        stop sits ABOVE entry, the take-profit BELOW."""
        levels = signal.metadata.get("key_levels") or {}
        entry = _pos_float(levels.get("entry"))
        stop = _pos_float(levels.get("stop_loss"))
        target = _pos_float(levels.get("take_profit"))
        atr = _pos_float(signal.metadata.get("atr"))  # absolute $ per share

        entry_ref = entry if entry is not None else price
        if entry_ref <= 0:
            return None

        resolved_stop = self._resolve_short_stop(entry_ref, stop, atr)
        if resolved_stop is None:
            return None

        # Size from the actual stop distance (positive fraction above entry).
        stop_frac = (resolved_stop - entry_ref) / entry_ref
        shares = self.position_sizer.calculate_shares(
            symbol=signal.symbol,
            price=entry_ref,
            portfolio=portfolio,
            stop_loss_pct=stop_frac,
            confidence=signal.confidence,
        )
        if shares <= 0:
            logger.debug(f"Short bracket size is 0 for {signal.symbol}")
            return None

        # Target BELOW entry. Use the LLM's if it's sane, else derive from RR.
        if target is not None and target < entry_ref:
            resolved_target = target
        else:
            resolved_target = entry_ref - self.default_risk_reward * (resolved_stop - entry_ref)
        # A stock can't trade below zero; clamp the derived target to a small
        # positive floor so the bracket leg is always valid.
        if resolved_target <= 0:
            resolved_target = round(entry_ref * 0.01, 2) or 0.01

        # A target entry ABOVE the current price rests as a LIMIT (sell the rip);
        # otherwise enter at market now.
        use_limit = entry is not None and entry > price

        logger.info(
            f"Risk approved: BRACKET SELL_SHORT {shares} {signal.symbol} "
            f"entry~{entry_ref:.2f} stop={resolved_stop:.2f} target={resolved_target:.2f} "
            f"(confidence={signal.confidence:.2f})"
        )
        return Order(
            symbol=signal.symbol,
            side=OrderSide.SELL_SHORT,
            qty=float(shares),
            order_type=OrderType.LIMIT if use_limit else OrderType.MARKET,
            limit_price=round(entry_ref, 2) if use_limit else None,
            order_class=OrderClass.BRACKET,
            take_profit_price=round(resolved_target, 2),
            stop_loss_price=round(resolved_stop, 2),
            time_in_force="gtc",
        )

    def _resolve_short_stop(
        self, entry: float, stop: float | None, atr: float | None
    ) -> float | None:
        """Resolve a short stop price: explicit level, else ATR-based, else None.

        Inverted from ``_resolve_stop``: the stop sits ABOVE entry and is clamped
        so it is never further than ``short_max_stop_distance_pct`` above entry
        (caps the per-trade loss)."""
        if stop is not None and stop > entry:
            resolved = stop
        elif atr is not None:
            resolved = entry + self.atr_stop_multiple * atr
        else:
            return None

        ceiling_stop = entry * (1 + self.short_max_stop_distance_pct)
        if resolved > ceiling_stop:
            resolved = ceiling_stop
        if resolved <= entry:
            return None
        return resolved

    def _handle_buy_to_cover(
        self,
        signal: TradeSignal,
        price: float,
        portfolio: PortfolioState,
    ) -> Order | None:
        """Close (cover) a short position, in full or part."""
        position = portfolio.positions.get(signal.symbol)
        if position is None or position.side != PositionSide.SHORT:
            logger.debug(f"No short position for {signal.symbol}, skipping cover")
            return None

        cover_pct = getattr(signal, "sell_pct", 1.0)
        cover_pct = max(0.0, min(1.0, cover_pct))
        qty = min(round(position.qty * cover_pct, 9), position.qty)
        if qty <= 0:
            logger.debug(
                f"Cover quantity rounds to 0 for {signal.symbol} "
                f"(cover_pct={cover_pct:.2f}), skipping"
            )
            return None

        logger.info(
            f"Risk approved: BUY_TO_COVER {qty} {signal.symbol} @ ~{price:.2f} "
            f"({cover_pct:.0%} of {position.qty} shares)"
        )
        return Order(
            symbol=signal.symbol,
            side=OrderSide.BUY_TO_COVER,
            qty=qty,
        )

    # ------------------------------------------------------------------ #
    # F9: human-order reception gate (FR-5). NEW path — distinct entry point
    # from evaluate_signal (agent path), sharing only helpers, so enriching the
    # human path can't regress the agent path. Receives a fully-specified
    # Alpaca-shaped Order, applies budget/pool/breaker + clamp + auto-protect +
    # price-sanity, and returns a structured OrderDecision.
    # ------------------------------------------------------------------ #
    def receive_human_order(
        self,
        order: Order,
        portfolio: PortfolioState,
        price: float | None,
        *,
        atr: float | None = None,
        force: bool = False,
    ) -> OrderDecision:
        # 0) capability gate — fail-closed, NOT overridable by force.
        if str(order.time_in_force).lower() not in _SUPPORTED_TIF:
            return OrderDecision(
                accepted=False, reason_code="UNSUPPORTED_TIF",
                message=f"time_in_force {order.time_in_force!r} not wired in v1 (day/gtc/ioc/fok)",
            )
        if order.order_class not in _SUPPORTED_CLASS:
            return OrderDecision(
                accepted=False, reason_code="UNSUPPORTED_CLASS",
                message=f"order_class {order.order_class.value} not wired in v1 (simple/bracket/oco)",
            )
        if price is None or price <= 0:
            return OrderDecision(
                accepted=False, reason_code="NO_PRICE",
                message=f"no usable price for {order.symbol}",
            )
        if order.side == OrderSide.BUY:
            return self._receive_human_buy(order, portfolio, price, atr, force)
        if order.side == OrderSide.SELL_SHORT:
            return self._receive_human_sell_short(order, portfolio, price, atr, force)
        if order.side == OrderSide.BUY_TO_COVER:
            return self._receive_human_buy_to_cover(order, portfolio, price, force)
        return self._receive_human_sell(order, portfolio, price, force)

    def _receive_human_buy(
        self, order: Order, portfolio: PortfolioState, price: float,
        atr: float | None, force: bool,
    ) -> OrderDecision:
        # 1) pool / breaker / no-add — overridable by an explicit force (FR-5a).
        if not force:
            if self._new_buys_halted:
                return OrderDecision(
                    accepted=False, reason_code="BREAKER_HALTED",
                    message="circuit breaker active; new buys halted",
                    suggestion={"force": True},
                )
            if portfolio.position_count >= self.max_open_positions:
                return OrderDecision(
                    accepted=False, reason_code="POOL_FULL",
                    message=f"max_open_positions ({self.max_open_positions}) reached",
                    suggestion={"force": True},
                )
            if order.symbol in portfolio.positions:
                return OrderDecision(
                    accepted=False, reason_code="ALREADY_HELD",
                    message=f"already holding {order.symbol}; not adding",
                    suggestion={"force": True},
                )

        # 2) entry reference for sizing + price-sanity (a resting limit buy uses
        #    its limit; otherwise current market).
        entry_ref = (
            order.limit_price
            if order.order_type == OrderType.LIMIT and order.limit_price
            else price
        )
        if entry_ref <= 0:
            return OrderDecision(accepted=False, reason_code="PRICE_SANITY",
                                 message="non-positive entry reference")

        # 3) price-sanity on caller-specified protective legs (long semantics) —
        #    NOT overridable by force.
        if order.stop_loss_price is not None and order.stop_loss_price >= entry_ref:
            return OrderDecision(
                accepted=False, reason_code="PRICE_SANITY",
                message=f"stop_loss {order.stop_loss_price} >= entry {entry_ref:.2f} for a long",
            )
        if order.take_profit_price is not None and order.take_profit_price <= entry_ref:
            return OrderDecision(
                accepted=False, reason_code="PRICE_SANITY",
                message=f"take_profit {order.take_profit_price} <= entry {entry_ref:.2f} for a long",
            )

        # 4) budget clamp — overridable by force.
        final_qty = order.qty
        if not force:
            stop = order.stop_loss_price
            stop_frac = (
                (entry_ref - stop) / entry_ref
                if stop is not None and 0 < stop < entry_ref
                else self.stop_loss_pct
            )
            budget_shares = self.position_sizer.calculate_shares(
                symbol=order.symbol, price=entry_ref, portfolio=portfolio,
                stop_loss_pct=stop_frac, confidence=1.0,
            )
            if budget_shares <= 0:
                return OrderDecision(
                    accepted=False, reason_code="NO_BUDGET",
                    message="risk budget / cash allows 0 shares",
                    suggestion={"force": True},
                )
            if order.qty > budget_shares:
                final_qty = float(budget_shares)
        if final_qty <= 0:
            return OrderDecision(accepted=False, reason_code="ZERO_QTY",
                                 message="quantity rounds to 0 shares")

        out = order.model_copy(update={"qty": final_qty})

        # 5) auto-protect: a plain SIMPLE market/limit buy with no legs becomes a
        #    resting BRACKET when a stop can be resolved (ATR/level). Otherwise it
        #    stays simple and the polled stop backup covers it.
        if (out.order_class == OrderClass.SIMPLE
                and out.order_type in (OrderType.MARKET, OrderType.LIMIT)
                and out.stop_loss_price is None and out.take_profit_price is None):
            resolved_stop = self._resolve_stop(entry_ref, None, atr)
            if resolved_stop is not None:
                target = entry_ref + self.default_risk_reward * (entry_ref - resolved_stop)
                out = out.model_copy(update={
                    "order_class": OrderClass.BRACKET,
                    "stop_loss_price": round(resolved_stop, 2),
                    "take_profit_price": round(target, 2),
                    "time_in_force": "gtc",
                })

        if final_qty != order.qty:
            return OrderDecision(
                accepted=True, order=out, reason_code="CLAMPED",
                message=f"qty {order.qty:g}->{final_qty:g} fits the risk budget",
                suggestion={"qty": final_qty},
            )
        return OrderDecision(accepted=True, order=out,
                             message=f"BUY {out.qty:g} {out.symbol}")

    def _receive_human_sell(
        self, order: Order, portfolio: PortfolioState, price: float, force: bool,
    ) -> OrderDecision:
        pos = portfolio.positions.get(order.symbol)
        if pos is None or pos.qty <= 0:
            return OrderDecision(accepted=False, reason_code="NO_POSITION",
                                 message=f"no position in {order.symbol}")
        # A protective sell STOP must sit below market or it exits immediately —
        # price-sanity, NOT overridable by force.
        if (order.order_type == OrderType.STOP and order.stop_price is not None
                and order.stop_price >= price):
            return OrderDecision(
                accepted=False, reason_code="PRICE_SANITY",
                message=f"sell stop {order.stop_price} >= market {price:.2f}; would exit immediately",
            )
        # Clamp to the held quantity (never oversell). qty<=0 means "full exit".
        final_qty = min(order.qty, pos.qty) if order.qty > 0 else pos.qty
        if final_qty <= 0:
            return OrderDecision(accepted=False, reason_code="ZERO_QTY",
                                 message="sell quantity rounds to 0")
        out = order.model_copy(update={"qty": final_qty})
        if order.qty > 0 and final_qty != order.qty:
            return OrderDecision(
                accepted=True, order=out, reason_code="CLAMPED",
                message=f"qty {order.qty:g}->{final_qty:g} (held position size)",
                suggestion={"qty": final_qty},
            )
        return OrderDecision(accepted=True, order=out,
                             message=f"SELL {final_qty:g} {out.symbol}")

    def _receive_human_sell_short(
        self, order: Order, portfolio: PortfolioState, price: float,
        atr: float | None, force: bool,
    ) -> OrderDecision:
        """Human short entry gate. Mirrors _receive_human_buy with inverted
        protective-leg geometry, plus the MANDATORY-stop rule (a human short
        with no resolvable stop is rejected, even with force — fail-closed)."""
        # 1) pool / breaker / no-add — overridable by force (except mandatory stop).
        if not force:
            if self._new_shorts_halted:
                return OrderDecision(
                    accepted=False, reason_code="BREAKER_HALTED",
                    message="circuit breaker active; new shorts halted",
                    suggestion={"force": True},
                )
            if portfolio.position_count >= self.max_open_positions:
                return OrderDecision(
                    accepted=False, reason_code="POOL_FULL",
                    message=f"max_open_positions ({self.max_open_positions}) reached",
                    suggestion={"force": True},
                )
        existing = portfolio.positions.get(order.symbol)
        if existing is not None:
            if existing.side == PositionSide.SHORT and not force:
                return OrderDecision(
                    accepted=False, reason_code="ALREADY_HELD",
                    message=f"already short {order.symbol}; not adding",
                    suggestion={"force": True},
                )
            if existing.side == PositionSide.LONG:
                return OrderDecision(
                    accepted=False, reason_code="HOLDING_LONG",
                    message=f"holding a long in {order.symbol}; close it before shorting",
                )

        # 2) entry reference (resting limit short uses its limit; else market).
        entry_ref = (
            order.limit_price
            if order.order_type == OrderType.LIMIT and order.limit_price
            else price
        )
        if entry_ref <= 0:
            return OrderDecision(accepted=False, reason_code="PRICE_SANITY",
                                 message="non-positive entry reference")

        # 3) price-sanity on caller-specified protective legs (short semantics) —
        #    NOT overridable by force. Stop ABOVE entry, target BELOW.
        if order.stop_loss_price is not None and order.stop_loss_price <= entry_ref:
            return OrderDecision(
                accepted=False, reason_code="PRICE_SANITY",
                message=f"stop_loss {order.stop_loss_price} <= entry {entry_ref:.2f} for a short",
            )
        if order.take_profit_price is not None and order.take_profit_price >= entry_ref:
            return OrderDecision(
                accepted=False, reason_code="PRICE_SANITY",
                message=f"take_profit {order.take_profit_price} >= entry {entry_ref:.2f} for a short",
            )

        # 4) budget clamp — overridable by force.
        final_qty = order.qty
        if not force:
            stop = order.stop_loss_price
            stop_frac = (
                (stop - entry_ref) / entry_ref
                if stop is not None and stop > entry_ref > 0
                else self.short_stop_loss_pct
            )
            budget_shares = self.position_sizer.calculate_shares(
                symbol=order.symbol, price=entry_ref, portfolio=portfolio,
                stop_loss_pct=stop_frac, confidence=1.0,
            )
            if budget_shares <= 0:
                return OrderDecision(
                    accepted=False, reason_code="NO_BUDGET",
                    message="risk budget / cash allows 0 shares",
                    suggestion={"force": True},
                )
            if order.qty > budget_shares:
                final_qty = float(budget_shares)
        if final_qty <= 0:
            return OrderDecision(accepted=False, reason_code="ZERO_QTY",
                                 message="quantity rounds to 0 shares")

        out = order.model_copy(update={"qty": final_qty})

        # 5) auto-protect: a plain SIMPLE short with no legs becomes a resting
        #    BRACKET when a stop can be resolved. Inverted geometry vs a long.
        if (out.order_class == OrderClass.SIMPLE
                and out.order_type in (OrderType.MARKET, OrderType.LIMIT)
                and out.stop_loss_price is None and out.take_profit_price is None):
            resolved_stop = self._resolve_short_stop(entry_ref, None, atr)
            if resolved_stop is not None:
                target = entry_ref - self.default_risk_reward * (resolved_stop - entry_ref)
                if target <= 0:
                    target = round(entry_ref * 0.01, 2) or 0.01
                out = out.model_copy(update={
                    "order_class": OrderClass.BRACKET,
                    "stop_loss_price": round(resolved_stop, 2),
                    "take_profit_price": round(target, 2),
                    "time_in_force": "gtc",
                })

        # 6) MANDATORY stop (FR-4.1) — fail-closed, NOT overridable by force. A
        #    short with no protective stop after auto-protect is rejected.
        if out.stop_loss_price is None:
            return OrderDecision(
                accepted=False, reason_code="NO_STOP",
                message=(
                    "short entry requires a stop-loss (give a level, or ensure "
                    "ATR is available for auto-protect); unbounded-loss guard"
                ),
            )

        if final_qty != order.qty:
            return OrderDecision(
                accepted=True, order=out, reason_code="CLAMPED",
                message=f"qty {order.qty:g}->{final_qty:g} fits the risk budget",
                suggestion={"qty": final_qty},
            )
        return OrderDecision(accepted=True, order=out,
                             message=f"SELL_SHORT {out.qty:g} {out.symbol}")

    def _receive_human_buy_to_cover(
        self, order: Order, portfolio: PortfolioState, price: float, force: bool,
    ) -> OrderDecision:
        """Human cover gate. Clamps to the held short and price-sanity-checks a
        protective cover STOP (must sit at/above market or it fires instantly)."""
        pos = portfolio.positions.get(order.symbol)
        if pos is None or pos.qty <= 0 or pos.side != PositionSide.SHORT:
            return OrderDecision(accepted=False, reason_code="NO_POSITION",
                                 message=f"no short position in {order.symbol}")
        # A protective cover STOP must be >= market or it covers immediately.
        if (order.order_type == OrderType.STOP and order.stop_price is not None
                and order.stop_price <= price):
            return OrderDecision(
                accepted=False, reason_code="PRICE_SANITY",
                message=f"cover stop {order.stop_price} <= market {price:.2f}; would cover immediately",
            )
        final_qty = min(order.qty, pos.qty) if order.qty > 0 else pos.qty
        if final_qty <= 0:
            return OrderDecision(accepted=False, reason_code="ZERO_QTY",
                                 message="cover quantity rounds to 0")
        out = order.model_copy(update={"qty": final_qty})
        if order.qty > 0 and final_qty != order.qty:
            return OrderDecision(
                accepted=True, order=out, reason_code="CLAMPED",
                message=f"qty {order.qty:g}->{final_qty:g} (held short size)",
                suggestion={"qty": final_qty},
            )
        return OrderDecision(accepted=True, order=out,
                             message=f"BUY_TO_COVER {final_qty:g} {out.symbol}")

    # ------------------------------------------------------------------ #
    # Stop adjustment (ADJUST_STOP, used by the agent path)
    # ------------------------------------------------------------------ #
    def ratchet_stop(
        self,
        current_stop: float,
        proposed_stop: float,
        allow_widen: bool = False,
        position_side: PositionSide = PositionSide.LONG,
    ) -> float:
        """A protective stop may only tighten unless widening is explicitly
        allowed. For a LONG, tighten = move UP (max); for a SHORT, tighten =
        move DOWN (min). Returns the effective stop price."""
        if allow_widen:
            return proposed_stop
        if position_side == PositionSide.SHORT:
            return min(current_stop, proposed_stop)
        return max(current_stop, proposed_stop)

    # ------------------------------------------------------------------ #
    # Polled backup exits
    # ------------------------------------------------------------------ #
    def check_stop_loss(
        self,
        portfolio: PortfolioState,
        protected_symbols: set[str] | None = None,
    ) -> list[Order]:
        """Check positions for stop-loss triggers.

        ``protected_symbols`` are positions already covered by a resting
        exchange-side stop; they are skipped so this polled check acts only as
        a backup for positions without resting protection.
        """
        protected = protected_symbols or set()
        orders = []
        for symbol, position in portfolio.positions.items():
            if symbol in protected:
                continue
            if position.avg_entry_price <= 0:
                continue
            if position.side == PositionSide.SHORT:
                # A short loses as price rises; exit by covering.
                loss_pct = (
                    (position.current_price - position.avg_entry_price)
                    / position.avg_entry_price
                )
                threshold = self.short_stop_loss_pct
                exit_side = OrderSide.BUY_TO_COVER
            else:
                loss_pct = (
                    (position.avg_entry_price - position.current_price)
                    / position.avg_entry_price
                )
                threshold = self.stop_loss_pct
                exit_side = OrderSide.SELL
            if loss_pct >= threshold:
                logger.warning(
                    f"Stop-loss triggered for {symbol} ({position.side.value}): "
                    f"loss={loss_pct:.1%} >= {threshold:.1%}"
                )
                orders.append(Order(
                    symbol=symbol,
                    side=exit_side,
                    qty=position.qty,
                ))
        return orders

    def check_take_profit(
        self,
        portfolio: PortfolioState,
        protected_symbols: set[str] | None = None,
    ) -> list[Order]:
        """Check positions for take-profit triggers (skips ``protected_symbols``
        already covered by a resting exchange-side take-profit)."""
        protected = protected_symbols or set()
        orders = []
        for symbol, position in portfolio.positions.items():
            if symbol in protected:
                continue
            if position.avg_entry_price <= 0:
                continue
            if position.side == PositionSide.SHORT:
                # A short profits as price falls; realize by covering.
                gain_pct = (
                    (position.avg_entry_price - position.current_price)
                    / position.avg_entry_price
                )
                threshold = self.short_take_profit_pct
                exit_side = OrderSide.BUY_TO_COVER
            else:
                gain_pct = (
                    (position.current_price - position.avg_entry_price)
                    / position.avg_entry_price
                )
                threshold = self.take_profit_pct
                exit_side = OrderSide.SELL
            if gain_pct >= threshold:
                logger.info(
                    f"Take-profit triggered for {symbol} ({position.side.value}): "
                    f"gain={gain_pct:.1%} >= {threshold:.1%}"
                )
                orders.append(Order(
                    symbol=symbol,
                    side=exit_side,
                    qty=position.qty,
                ))
        return orders

from __future__ import annotations

from typing import Any

from loguru import logger

from src.core.exceptions import RiskLimitError
from src.core.models import Order, PortfolioState, TradeSignal
from src.core.types import OrderClass, OrderSide, OrderType, Signal
from src.risk.position_sizer import PositionSizer


def _pos_float(value: Any) -> float | None:
    """Coerce an LLM-supplied level to a positive float, else None."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


class RiskManager:
    """Manages risk by validating orders and enforcing limits.

    When ``use_bracket_orders`` is enabled, a BUY whose signal carries levels
    (``signal.metadata["key_levels"]`` with entry/stop_loss/take_profit, plus an
    optional absolute ``signal.metadata["atr"]``) becomes a resting BRACKET
    order: a guardrailed stop, a take-profit (LLM's or derived from
    ``default_risk_reward``), and a size derived from the *actual* stop distance
    (so per-trade risk is capped at ``max_portfolio_risk`` instead of being
    computed against a fixed assumed stop).

    It is **disabled by default** so the legacy market-order + polled-stop path
    is byte-for-byte unchanged until the agent orchestrator opts in (Phase 3),
    which also supplies ``protected_symbols`` to the stop/take checks so a
    resting bracket and the polled backup never double-exit the same position.
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
    ):
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_open_positions = max_open_positions
        self.max_stop_distance_pct = max_stop_distance_pct
        self.atr_stop_multiple = atr_stop_multiple
        self.market_halt_threshold_pct = market_halt_threshold_pct
        self.default_risk_reward = default_risk_reward
        self.use_bracket_orders = use_bracket_orders
        self._new_buys_halted = False
        self.position_sizer = PositionSizer(
            max_position_pct=max_position_pct,
            max_portfolio_risk=max_portfolio_risk,
        )

    # ------------------------------------------------------------------ #
    # Circuit breaker
    # ------------------------------------------------------------------ #
    def update_market_halt(self, spy_change_pct: float | None) -> None:
        """Halt new buys when the market's day-change is at/below the breaker
        threshold. The caller (engine/orchestrator) supplies SPY's day-change
        each cycle; RiskManager stays free of data access."""
        halted = (
            spy_change_pct is not None
            and spy_change_pct <= self.market_halt_threshold_pct
        )
        if halted and not self._new_buys_halted:
            logger.warning(
                f"Circuit breaker tripped: halting new buys "
                f"(market {spy_change_pct:.2%} <= {self.market_halt_threshold_pct:.2%})"
            )
        elif self._new_buys_halted and not halted:
            logger.info("Circuit breaker cleared: new buys re-enabled")
        self._new_buys_halted = halted

    @property
    def new_buys_halted(self) -> bool:
        return self._new_buys_halted

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
        else:
            return self._handle_sell(signal, price, portfolio)

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

        qty = int(position.qty * sell_pct)
        if qty <= 0:
            qty = 1  # Minimum 1 share

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
    # Stop adjustment (ADJUST_STOP, used by the agent path in Phase 3)
    # ------------------------------------------------------------------ #
    def ratchet_stop(
        self,
        current_stop: float,
        proposed_stop: float,
        allow_widen: bool = False,
    ) -> float:
        """A long position's protective stop may only move up (tighten) unless
        widening is explicitly allowed. Returns the effective stop price."""
        if allow_widen:
            return proposed_stop
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
            loss_pct = (position.avg_entry_price - position.current_price) / position.avg_entry_price
            if loss_pct >= self.stop_loss_pct:
                logger.warning(
                    f"Stop-loss triggered for {symbol}: "
                    f"loss={loss_pct:.1%} >= {self.stop_loss_pct:.1%}"
                )
                orders.append(Order(
                    symbol=symbol,
                    side=OrderSide.SELL,
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
            gain_pct = (position.current_price - position.avg_entry_price) / position.avg_entry_price
            if gain_pct >= self.take_profit_pct:
                logger.info(
                    f"Take-profit triggered for {symbol}: "
                    f"gain={gain_pct:.1%} >= {self.take_profit_pct:.1%}"
                )
                orders.append(Order(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    qty=position.qty,
                ))
        return orders

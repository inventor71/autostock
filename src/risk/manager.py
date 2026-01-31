from __future__ import annotations

import logging

from src.core.exceptions import RiskLimitError
from src.core.models import Order, PortfolioState, TradeSignal
from src.core.types import OrderSide, Signal
from src.risk.position_sizer import PositionSizer

logger = logging.getLogger(__name__)


class RiskManager:
    """Manages risk by validating orders and enforcing limits."""

    def __init__(
        self,
        max_position_pct: float = 0.1,
        max_portfolio_risk: float = 0.02,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.15,
        max_open_positions: int = 10,
    ):
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_open_positions = max_open_positions
        self.position_sizer = PositionSizer(
            max_position_pct=max_position_pct,
            max_portfolio_risk=max_portfolio_risk,
        )

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

        # Calculate position size
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

        logger.info(
            f"Risk approved: SELL {position.qty} {signal.symbol} @ ~{price:.2f}"
        )

        return Order(
            symbol=signal.symbol,
            side=OrderSide.SELL,
            qty=position.qty,
        )

    def check_stop_loss(
        self,
        portfolio: PortfolioState,
    ) -> list[Order]:
        """Check all positions for stop-loss triggers."""
        orders = []
        for symbol, position in portfolio.positions.items():
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
    ) -> list[Order]:
        """Check all positions for take-profit triggers."""
        orders = []
        for symbol, position in portfolio.positions.items():
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

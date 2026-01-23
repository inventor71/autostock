from __future__ import annotations

from loguru import logger

from src.core.models import PortfolioState


class PositionSizer:
    """Calculates position sizes based on risk parameters."""

    def __init__(
        self,
        max_position_pct: float = 0.1,
        max_portfolio_risk: float = 0.02,
    ):
        self.max_position_pct = max_position_pct
        self.max_portfolio_risk = max_portfolio_risk

    def calculate_shares(
        self,
        symbol: str,
        price: float,
        portfolio: PortfolioState,
        stop_loss_pct: float = 0.05,
        confidence: float = 0.5,
    ) -> int:
        """Calculate the number of shares to buy.

        Uses fixed-fraction position sizing with risk-based adjustment.

        Args:
            symbol: Ticker symbol.
            price: Current stock price.
            portfolio: Current portfolio state.
            stop_loss_pct: Stop loss percentage for risk calculation.
            confidence: Signal confidence (0-1) to scale position size.

        Returns:
            Number of whole shares to buy.
        """
        if price <= 0:
            return 0

        total_equity = portfolio.equity
        if total_equity <= 0:
            return 0

        # Max allocation for this position
        max_allocation = total_equity * self.max_position_pct

        # Risk-based sizing: risk per trade = portfolio_risk / stop_loss
        risk_amount = total_equity * self.max_portfolio_risk
        risk_based_allocation = risk_amount / stop_loss_pct if stop_loss_pct > 0 else max_allocation

        # Take the smaller of the two
        allocation = min(max_allocation, risk_based_allocation)

        # Scale by confidence
        allocation *= confidence

        # Don't exceed available cash
        allocation = min(allocation, portfolio.cash)

        shares = int(allocation / price)

        logger.debug(
            f"Position sizing for {symbol}: price={price:.2f}, "
            f"allocation={allocation:.2f}, shares={shares}"
        )

        return shares

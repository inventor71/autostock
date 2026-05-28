from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from src.core.models import FilledOrder, OpenOrder, Order, Position, PortfolioState


class BaseBroker(ABC):
    """Abstract base class for all brokers."""

    def get_open_orders(self, symbol: str | None = None) -> list[OpenOrder]:
        """List resting (open) orders, optionally for one symbol.

        Used to reconcile resting protective legs (so polled stop/take-profit
        checks act only as a backup) and to find the order to cancel/replace on
        an ADJUST_STOP. Default returns [] for brokers that don't track them.
        """
        return []

    def is_market_open(self) -> bool:
        """Whether the regular session is open right now. Order placement is
        gated on this for the live agent path. Default True (simulated/backtest
        brokers are always 'open')."""
        return True

    def record_trade_ledger(
        self,
        path: str | Path,
        *,
        since: str | None = None,
        min_notional: float = 0.0,
    ) -> None:
        """Reconstruct closed round-trips from broker history and append them
        to the trades ledger at ``path`` (one JSON line per round-trip).

        Live brokers (e.g. Alpaca) override this to query their activities/fills
        history. Simulated/backtest brokers track trades in their own way and
        this is a no-op for them. Callers should invoke unconditionally — the
        no-op default means callers no longer need to type-check the broker.
        """
        return None

    @abstractmethod
    def submit_order(self, order: Order) -> FilledOrder:
        """Submit an order for execution."""
        pass

    @abstractmethod
    def get_position(self, symbol: str) -> Position | None:
        """Get current position for a symbol."""
        pass

    @abstractmethod
    def get_all_positions(self) -> list[Position]:
        """Get all open positions."""
        pass

    @abstractmethod
    def get_portfolio_state(self) -> PortfolioState:
        """Get current portfolio state including cash and equity."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        pass

    @abstractmethod
    def close_position(self, symbol: str) -> FilledOrder | None:
        """Close an existing position entirely."""
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> FilledOrder | None:
        """Query latest fill state of a previously submitted order.

        Returns FilledOrder with current filled_price/qty (may be 0 if still pending),
        or None if the order does not exist.
        """
        pass

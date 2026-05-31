from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from src.agent.intraday.records import FillEvent
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

    def get_fills(self, since: str | None = None) -> list[FillEvent]:
        """Broker fill events after ``since`` (an opaque, broker-specific cursor).

        Used by the F3 snapshot publisher to detect *new fills* for the new-fill
        wake (FR-4-A) — keyed by the broker activity id so partial fills stay
        distinct and the cursor is idempotent. Default returns [] for brokers
        that don't expose a fill/activity feed (simulated/backtest); live brokers
        (Alpaca) override it. Read-only — never places orders (advisor-only)."""
        return []

    def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        """Latest trade price per symbol (F8 sidebar: current price + Δ-to-trigger
        for resting orders on symbols we don't hold). Default {} for brokers
        without a market-data feed (simulated/backtest); Alpaca overrides it.
        Read-only, best-effort — callers tolerate missing symbols (NFR-4)."""
        return {}

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

    # ------------------------------------------------------------------ #
    # F9: structured order management (Alpaca-shaped). Defaults emulate via
    # the single-target primitives so simulated/backtest brokers work unchanged;
    # live brokers (Alpaca) override with native calls.
    # ------------------------------------------------------------------ #
    def replace_order(self, order_id: str, changes: dict) -> FilledOrder | None:
        """Replace (modify) a resting order's qty/limit/stop/trail/TIF in place.

        Default is unsupported (returns None) — only brokers with a native
        replace endpoint implement it. F9 (Q2=A) restricts replace to SIMPLE
        resting orders; the daemon rejects a replace targeting a bracket/OCO leg
        before reaching here. ``changes`` may contain qty/limit_price/stop_price/
        trail/time_in_force.
        """
        return None

    def cancel_all_orders(self, symbol: str | None = None) -> int:
        """Cancel all resting orders (optionally for one symbol). Returns the
        count cancelled. Default emulates by looping ``get_open_orders`` +
        ``cancel_order`` so every broker has the capability."""
        opens = self.get_open_orders(symbol)
        n = 0
        for o in opens:
            if self.cancel_order(o.order_id):
                n += 1
        return n

    def close_all_positions(self, cancel_orders: bool = True) -> list[FilledOrder]:
        """Close every open position. When ``cancel_orders`` is True, resting
        orders are cancelled first so their qty is released before the close.
        Default emulates by looping ``get_all_positions`` + ``close_position``."""
        if cancel_orders:
            self.cancel_all_orders()
        out: list[FilledOrder] = []
        for pos in self.get_all_positions():
            filled = self.close_position(pos.symbol)
            if filled is not None:
                out.append(filled)
        return out

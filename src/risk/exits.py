"""Polled stop/take-profit backup: the single implementation.

Replaces three near-duplicate copies that the project had grown:

- ``TradingEngine._check_risk_exits``      — whole portfolio per cycle
- ``TradingEngine._check_symbol_risk_exit`` — one symbol per streamed bar
- ``DecisionExecutor.run_risk_exits``      — agent backup, skips resting protection

They all do the same dance (refresh prices, ask RiskManager, submit exits); only
the *scope* differs. This module is the one implementation; the three callers
delegate. (AI-DLC structural finding S-1.)
"""

from __future__ import annotations

from loguru import logger

from src.core.models import FilledOrder, PortfolioState
from src.data.prices import fetch_latest_prices
from src.execution.base import BaseBroker
from src.risk.manager import RiskManager


def run_polled_exits(
    risk_manager: RiskManager,
    broker: BaseBroker,
    portfolio: PortfolioState,
    *,
    data_provider=None,
    symbol: str | None = None,
    latest_price: float | None = None,
    protected_symbols: set[str] | None = None,
) -> list[FilledOrder]:
    """Refresh prices, ask the RiskManager which positions to exit, place those exits.

    Args:
        risk_manager: the risk gate that owns the stop/take-profit thresholds.
        broker: where exit orders are submitted.
        portfolio: the portfolio to check; this function mutates each in-scope
            ``Position.current_price`` as a side effect of refreshing.
        data_provider: source for the latest price; needed unless ``latest_price``
            is supplied (single-symbol case). When ``None`` and ``symbol`` is also
            ``None``, prices are not refreshed (caller already did so).
        symbol: when set, only that symbol's price is refreshed and only that
            symbol's exits are submitted (the other positions may have stale
            prices and are left untouched). When ``None``, the whole portfolio
            is checked.
        latest_price: a streamed-bar price for ``symbol``; avoids an extra fetch.
        protected_symbols: positions already covered by a resting exchange-side
            stop/take. They are skipped so the polled backup never double-exits
            a position the bracket order already handles.

    Returns:
        the FilledOrders for any exits that fired.
    """
    if symbol is None:
        # Whole-portfolio cycle: refresh every position's price. Fetches run
        # concurrently (same per-symbol calls, value-preserving); a single failed
        # fetch yields None and is skipped so it never sinks the whole check.
        if data_provider is not None:
            prices = fetch_latest_prices(data_provider, list(portfolio.positions))
            for sym, price in prices.items():
                if price is not None:
                    portfolio.positions[sym].update_price(price)
    else:
        # Per-symbol path (e.g. realtime bar): only that position is refreshed.
        position = portfolio.positions.get(symbol)
        if position is None:
            return []
        price = latest_price
        if price is None and data_provider is not None:
            try:
                price = data_provider.get_latest_price(symbol)
            except Exception as e:
                logger.error(f"Failed to get price for {symbol}: {e}")
                return []
        if price is not None:
            position.update_price(price)

    # Per-symbol stop levels for brokers that emulate the stop off-exchange (KIS
    # paper): the polled exit then fires at the agent's level, not the flat pct.
    stop_overrides: dict[str, float] = {}
    getter = getattr(broker, "get_protective_stops", None)
    if getter is not None:
        try:
            stop_overrides = getter()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"get_protective_stops failed: {e}")

    # Symbols whose take-profit leg is already resting at the exchange (KIS
    # emulated-OCO LIMIT sell). They are skipped by the polled TP check so a
    # market sell at the flat pct doesn't undercut the agent's intended price.
    tp_protected: set[str] | None = None
    oco_getter = getattr(broker, "get_oco_armed_symbols", None)
    if oco_getter is not None:
        try:
            armed = oco_getter()
            if armed:
                tp_protected = armed
        except Exception as e:  # noqa: BLE001
            logger.debug(f"get_oco_armed_symbols failed: {e}")

    exit_orders = (
        risk_manager.check_stop_loss(portfolio, protected_symbols, stop_overrides)
        + risk_manager.check_take_profit(portfolio, protected_symbols, tp_protected)
    )

    filled: list[FilledOrder] = []
    for order in exit_orders:
        # When called per-symbol, other positions may have stale prices and the
        # RiskManager scans the whole portfolio — keep only this symbol's exits.
        if symbol is not None and order.symbol != symbol:
            continue
        try:
            filled.append(broker.submit_order(order))
        except Exception as e:
            logger.error(f"Risk exit execution failed for {order.symbol}: {e}")
    return filled

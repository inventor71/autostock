from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd
from loguru import logger

from src.backtest.metrics import generate_report
from src.core.exceptions import InsufficientDataError
from src.core.models import BacktestResult, Order, PortfolioState
from src.core.types import OrderSide, Signal
from src.execution.brokers.simulated import SimulatedBroker
from src.risk.manager import RiskManager
from src.strategy.base import BaseStrategy

if TYPE_CHECKING:
    from loguru import Logger


class BacktestEngine:
    """Vectorized backtesting engine.

    Iterates through historical data bar-by-bar, generates signals
    from the strategy, applies risk management, and executes through
    the simulated broker.
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        initial_capital: float = 100000.0,
        commission_pct: float = 0.0,
        risk_config: dict | None = None,
        bt_logger: Logger | None = None,
    ):
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct
        self._logger = bt_logger or logger
        self.broker = SimulatedBroker(
            initial_capital=initial_capital,
            commission_pct=commission_pct,
        )
        risk_cfg = risk_config or {}
        self.risk_manager = RiskManager(
            max_position_pct=risk_cfg.get("max_position_pct", 0.1),
            max_portfolio_risk=risk_cfg.get("max_portfolio_risk", 0.02),
            stop_loss_pct=risk_cfg.get("stop_loss_pct", 0.05),
            take_profit_pct=risk_cfg.get("take_profit_pct", 0.15),
            max_open_positions=risk_cfg.get("max_open_positions", 10),
        )

    def run(
        self,
        universe: str | list[str],
        bars: pd.DataFrame | dict[str, pd.DataFrame],
        warmup_period: int | None = None,
    ) -> BacktestResult:
        """Run backtest on historical bar data.

        Supports both single-symbol (backward compatible) and multi-symbol modes:
        - Single: run("AAPL", bars_df) - original API
        - Multi: run(["AAPL", "MSFT"], {"AAPL": bars1, "MSFT": bars2})

        Args:
            universe: Single symbol string or list of symbols.
            bars: DataFrame for single symbol, or dict mapping symbol to DataFrame.
            warmup_period: Number of initial bars to skip for indicator warmup.
                          If None, uses 50 (slow MA default).

        Returns:
            BacktestResult with performance metrics and equity curve.
        """
        # Normalize to multi-symbol format
        if isinstance(universe, str):
            universe = [universe]
            bars_dict = {universe[0]: bars}
        else:
            bars_dict = bars

        if warmup_period is None:
            warmup_period = 50

        # Use first symbol's bars to determine date range
        reference_symbol = universe[0]
        reference_bars = bars_dict[reference_symbol]

        if len(reference_bars) <= warmup_period:
            raise InsufficientDataError(
                f"Need more than {warmup_period} bars, got {len(reference_bars)}"
            )

        self.broker.reset()
        equity_curve = []
        trades = []

        self._logger.info(
            f"Backtesting {self.strategy.name} on {len(universe)} symbols: "
            f"{len(reference_bars)} bars, warmup={warmup_period}"
        )

        for i in range(warmup_period, len(reference_bars)):
            # Update prices for all symbols
            for symbol in universe:
                symbol_bars = bars_dict.get(symbol)
                if symbol_bars is None or i >= len(symbol_bars):
                    continue
                price = float(symbol_bars.iloc[i]["close"])
                self.broker.set_current_price(symbol, price)

            # Get portfolio state
            portfolio = self.broker.get_portfolio_state()

            # Check stop-loss and take-profit
            sl_orders = self.risk_manager.check_stop_loss(portfolio)
            tp_orders = self.risk_manager.check_take_profit(portfolio)
            for order in sl_orders + tp_orders:
                try:
                    filled = self.broker.submit_order(order)
                    trades.append({
                        "symbol": filled.symbol,
                        "side": filled.side.value,
                        "qty": filled.qty,
                        "price": filled.filled_price,
                        "timestamp": reference_bars.index[i],
                        "pnl": self._calc_trade_pnl(filled, portfolio),
                    })
                except Exception as e:
                    self._logger.debug(f"SL/TP order failed: {e}")

            # Build market data dict for symbol selection
            market_data = {}
            for symbol in universe:
                symbol_bars = bars_dict.get(symbol)
                if symbol_bars is not None and i < len(symbol_bars):
                    market_data[symbol] = symbol_bars.iloc[:i + 1]

            # Strategy selects symbols if it supports selection
            if self.strategy.supports_selection():
                try:
                    selected_symbols = self.strategy.select_symbols(
                        universe, market_data, portfolio
                    )
                except Exception as e:
                    self._logger.debug(f"Symbol selection failed: {e}")
                    selected_symbols = universe
            else:
                selected_symbols = universe

            # Generate signals for selected symbols
            portfolio = self.broker.get_portfolio_state()
            for symbol in selected_symbols:
                history = market_data.get(symbol)
                if history is None or history.empty:
                    continue

                try:
                    signal = self.strategy.generate_signal(symbol, history, portfolio)
                except InsufficientDataError:
                    continue

                price = float(history.iloc[-1]["close"])
                order = self.risk_manager.evaluate_signal(signal, price, portfolio)

                if order is not None:
                    try:
                        filled = self.broker.submit_order(order)
                        trades.append({
                            "symbol": symbol,
                            "side": filled.side.value,
                            "qty": filled.qty,
                            "price": filled.filled_price,
                            "timestamp": reference_bars.index[i],
                            "pnl": self._calc_trade_pnl(filled, portfolio),
                        })
                        # Refresh portfolio after each trade
                        portfolio = self.broker.get_portfolio_state()
                    except Exception as e:
                        self._logger.debug(f"Order failed: {e}")

            # Record equity
            portfolio = self.broker.get_portfolio_state()
            equity_curve.append(portfolio.equity)

        # Build result
        equity_series = pd.Series(
            equity_curve, index=reference_bars.index[warmup_period:]
        )
        report = generate_report(equity_series, trades, self.initial_capital)

        result = BacktestResult(
            strategy_name=self.strategy.name,
            start_date=reference_bars.index[0].to_pydatetime(),
            end_date=reference_bars.index[-1].to_pydatetime(),
            initial_capital=self.initial_capital,
            final_capital=report["final_capital"],
            total_return_pct=report["total_return_pct"],
            sharpe_ratio=report["sharpe_ratio"],
            max_drawdown_pct=report["max_drawdown_pct"],
            total_trades=report["total_trades"],
            win_rate=report["win_rate"],
            profit_factor=report["profit_factor"],
            equity_curve=equity_curve,
        )

        self._logger.info(
            f"Backtest complete: return={result.total_return_pct:.2f}%, "
            f"sharpe={result.sharpe_ratio:.2f}, maxDD={result.max_drawdown_pct:.2f}%, "
            f"trades={result.total_trades}"
        )

        return result

    def _calc_trade_pnl(self, filled, portfolio: PortfolioState) -> float:
        """Calculate PnL for a sell trade."""
        if filled.side == OrderSide.SELL:
            pos = portfolio.positions.get(filled.symbol)
            if pos:
                return (filled.filled_price - pos.avg_entry_price) * filled.qty
        return 0.0

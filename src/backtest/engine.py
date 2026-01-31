from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from src.backtest.metrics import generate_report
from src.core.exceptions import InsufficientDataError
from src.core.models import BacktestResult, Order, PortfolioState
from src.core.types import OrderSide, Signal
from src.execution.brokers.simulated import SimulatedBroker
from src.risk.manager import RiskManager
from src.strategy.base import BaseStrategy

logger = logging.getLogger(__name__)


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
        bt_logger: logging.Logger | None = None,
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
        symbol: str,
        bars: pd.DataFrame,
        warmup_period: int | None = None,
    ) -> BacktestResult:
        """Run backtest on historical bar data.

        Args:
            symbol: Ticker symbol.
            bars: DataFrame with OHLCV data and DatetimeIndex.
            warmup_period: Number of initial bars to skip for indicator warmup.
                          If None, uses 50 (slow MA default).

        Returns:
            BacktestResult with performance metrics and equity curve.
        """
        if warmup_period is None:
            warmup_period = 50

        if len(bars) <= warmup_period:
            raise InsufficientDataError(
                f"Need more than {warmup_period} bars, got {len(bars)}"
            )

        self.broker.reset()
        equity_curve = []
        trades = []

        self._logger.info(
            f"Backtesting {self.strategy.name} on {symbol}: "
            f"{len(bars)} bars, warmup={warmup_period}"
        )

        for i in range(warmup_period, len(bars)):
            current_bar = bars.iloc[i]
            price = float(current_bar["close"])
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
                        "symbol": symbol,
                        "side": filled.side.value,
                        "qty": filled.qty,
                        "price": filled.filled_price,
                        "timestamp": bars.index[i],
                        "pnl": self._calc_trade_pnl(filled, portfolio),
                    })
                except Exception as e:
                    self._logger.debug(f"SL/TP order failed: {e}")

            # Generate signal from strategy
            history = bars.iloc[:i + 1]
            try:
                signal = self.strategy.generate_signal(symbol, history, portfolio)
            except InsufficientDataError:
                equity_curve.append(portfolio.equity)
                continue

            # Risk evaluation
            portfolio = self.broker.get_portfolio_state()
            order = self.risk_manager.evaluate_signal(signal, price, portfolio)

            if order is not None:
                try:
                    filled = self.broker.submit_order(order)
                    trades.append({
                        "symbol": symbol,
                        "side": filled.side.value,
                        "qty": filled.qty,
                        "price": filled.filled_price,
                        "timestamp": bars.index[i],
                        "pnl": self._calc_trade_pnl(filled, portfolio),
                    })
                except Exception as e:
                    self._logger.debug(f"Order failed: {e}")

            # Record equity
            portfolio = self.broker.get_portfolio_state()
            equity_curve.append(portfolio.equity)

        # Build result
        equity_series = pd.Series(equity_curve, index=bars.index[warmup_period:])
        report = generate_report(equity_series, trades, self.initial_capital)

        result = BacktestResult(
            strategy_name=self.strategy.name,
            start_date=bars.index[0].to_pydatetime(),
            end_date=bars.index[-1].to_pydatetime(),
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

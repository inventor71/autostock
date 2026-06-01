from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd
from loguru import logger

from src.backtest.metrics import generate_report
from src.core.exceptions import InsufficientDataError
from src.core.models import BacktestResult, FilledOrder, Order
from src.core.trades import match_round_trips
from src.core.types import OrderClass, OrderSide
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
            max_stop_distance_pct=risk_cfg.get("max_stop_distance_pct", 0.12),
            atr_stop_multiple=risk_cfg.get("atr_stop_multiple", 3.0),
            market_halt_threshold_pct=risk_cfg.get("market_halt_threshold_pct", -0.03),
            default_risk_reward=risk_cfg.get("default_risk_reward", 2.5),
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
        # Every fill (entries + exits) in match_round_trips format, so metrics
        # are computed from closed round-trips -- not by counting each fill as a
        # "trade" (which doubled the count and halved the win rate).
        fills: list[dict] = []
        filled_orders: list[FilledOrder] = []

        def _record(fo: FilledOrder | None, ts) -> None:
            if fo is None or fo.qty <= 0:
                return
            filled_orders.append(fo)
            fills.append({
                "symbol": fo.symbol,
                "side": fo.side.value,
                "qty": float(fo.qty),
                "price": float(fo.filled_price),
                "ts": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            })

        self._logger.info(
            f"Backtesting {self.strategy.name} on {len(universe)} symbols: "
            f"{len(reference_bars)} bars, warmup={warmup_period}"
        )

        # R2 C-1a/C-1b: when the strategy exposes a causal precompute fast-path AND
        # does no dynamic selection, precompute full-series indicators once and
        # answer each bar in O(1) — skipping both the per-bar slice copy and the
        # per-bar indicator recompute (the old O(n^2)). The fast-path is required
        # to match generate_signal exactly (enforced by the backtest golden); any
        # other strategy keeps the original slice + generate_signal path unchanged.
        use_fast_path = (
            self.strategy.supports_precompute()
            and not self.strategy.supports_selection()
        )
        if use_fast_path:
            for symbol in universe:
                sb = bars_dict.get(symbol)
                if sb is not None:
                    self.strategy.precompute(symbol, sb)

        for i in range(warmup_period, len(reference_bars)):
            ts = reference_bars.index[i]

            # Advance prices with the bar's intra-bar range so resting protective
            # orders trigger on the high/low like a real exchange (gap-safe) --
            # the same way the live agent's brackets fire at Alpaca. Capture any
            # exits the bar triggered.
            for symbol in universe:
                symbol_bars = bars_dict.get(symbol)
                if symbol_bars is None or i >= len(symbol_bars):
                    continue
                row = symbol_bars.iloc[i]
                for exit_fill in self.broker.set_current_price(
                    symbol, float(row["close"]),
                    high=float(row["high"]), low=float(row["low"]),
                ):
                    _record(exit_fill, ts)

            # Build look-ahead-safe market data for selection + signals. The
            # fast-path skips this per-bar slice copy entirely (C-1a).
            if use_fast_path:
                portfolio = self.broker.get_portfolio_state()
                selected_symbols = universe
            else:
                market_data = {}
                for symbol in universe:
                    symbol_bars = bars_dict.get(symbol)
                    if symbol_bars is not None and i < len(symbol_bars):
                        market_data[symbol] = symbol_bars.iloc[:i + 1]

                portfolio = self.broker.get_portfolio_state()
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

            for symbol in selected_symbols:
                if use_fast_path:
                    symbol_bars = bars_dict.get(symbol)
                    if symbol_bars is None or i >= len(symbol_bars):
                        continue
                    try:
                        signal = self.strategy.generate_signal_at(
                            symbol, symbol_bars, i, portfolio
                        )
                    except InsufficientDataError:
                        continue
                    price = float(symbol_bars.iloc[i]["close"])
                else:
                    history = market_data.get(symbol)
                    if history is None or history.empty:
                        continue
                    try:
                        signal = self.strategy.generate_signal(symbol, history, portfolio)
                    except InsufficientDataError:
                        continue
                    price = float(history.iloc[-1]["close"])

                order = self.risk_manager.evaluate_signal(signal, price, portfolio)
                if order is None:
                    continue

                # A discretionary sell must clear any resting protection first
                # (mirrors the live executor's cancel-then-act) so stale OCO legs
                # don't fire on a position the strategy already exited.
                if order.side == OrderSide.SELL:
                    for o in self.broker.get_open_orders(symbol):
                        self.broker.cancel_order(o.order_id)

                try:
                    filled = self.broker.submit_order(order)
                except Exception as e:
                    self._logger.debug(f"Order failed: {e}")
                    continue
                _record(filled, ts)

                # After an entry, arm a resting OCO (stop + take-profit) so exits
                # trigger intra-bar at the simulated exchange -- the same path the
                # live agent uses, instead of a close-only polled check.
                if order.side == OrderSide.BUY and filled.qty > 0:
                    _record(self._arm_protection(symbol, filled), ts)

                portfolio = self.broker.get_portfolio_state()

            equity_curve.append(self.broker.get_portfolio_state().equity)

        # Metrics from closed round-trips (FIFO match), shared with the live ledger.
        round_trips = match_round_trips(fills)
        trades_for_metrics = [{**rt, "pnl": rt["realized_pnl"]} for rt in round_trips]
        equity_series = pd.Series(
            equity_curve, index=reference_bars.index[warmup_period:]
        )
        report = generate_report(equity_series, trades_for_metrics, self.initial_capital)

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
            trades=filled_orders,
        )

        self._logger.info(
            f"Backtest complete: return={result.total_return_pct:.2f}%, "
            f"sharpe={result.sharpe_ratio:.2f}, maxDD={result.max_drawdown_pct:.2f}%, "
            f"trades={result.total_trades}"
        )

        return result

    def _arm_protection(self, symbol: str, entry_fill: FilledOrder) -> FilledOrder | None:
        """Arm a resting OCO (stop-loss + take-profit) on a freshly entered
        position, at the RiskManager's configured percentages off the fill price.

        This makes the backtest exit positions the same way the live agent does
        -- a resting bracket the exchange triggers intra-bar -- rather than a
        close-only polled stop. Returns the protective fill if the order
        triggered on the same bar (rare), else None.
        """
        entry = entry_fill.filled_price
        stop = round(entry * (1 - self.risk_manager.stop_loss_pct), 2)
        target = round(entry * (1 + self.risk_manager.take_profit_pct), 2)
        try:
            return self.broker.submit_order(Order(
                symbol=symbol,
                side=OrderSide.SELL,
                qty=entry_fill.qty,
                order_class=OrderClass.OCO,
                take_profit_price=target,
                stop_loss_price=stop,
            ))
        except Exception as e:
            self._logger.debug(f"Could not arm protection for {symbol}: {e}")
            return None

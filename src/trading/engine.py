from __future__ import annotations

import pandas as pd
from loguru import logger

from src.core.exceptions import InsufficientDataError
from src.core.models import FilledOrder, Order, PortfolioState, TradeSignal
from src.core.types import Signal, TimeFrame
from src.data.base import BaseDataProvider
from src.execution.base import BaseBroker
from src.risk.manager import RiskManager
from src.strategy.base import BaseStrategy


class TradingEngine:
    """Main orchestrator that connects data, strategy, risk, and execution.

    Flow: Data -> Strategy -> Risk Manager -> Broker

    The engine supports universe-based dynamic symbol selection:
    - `universe` defines the pool of tradeable symbols
    - Strategies can implement `select_symbols()` to dynamically choose
      which symbols to trade from the universe
    """

    def __init__(
        self,
        data_provider: BaseDataProvider,
        broker: BaseBroker,
        strategies: list[BaseStrategy],
        risk_manager: RiskManager,
        universe: list[str],
        timeframe: TimeFrame = TimeFrame.DAY_1,
        lookback: int = 100,
    ):
        self.data_provider = data_provider
        self.broker = broker
        self.strategies = strategies
        self.risk_manager = risk_manager
        self.universe = universe
        self.timeframe = timeframe
        self.lookback = lookback

    def run_cycle(self) -> list[FilledOrder]:
        """Execute one trading cycle for all symbols and strategies.

        Returns list of filled orders from this cycle.
        """
        filled_orders = []
        portfolio = self.broker.get_portfolio_state()

        # Check stop-loss / take-profit first
        self._check_risk_exits(portfolio, filled_orders)

        # Load market data for entire universe
        market_data = self._load_market_data()

        # Process each strategy
        for strategy in self.strategies:
            # Determine which symbols this strategy will trade
            if strategy.supports_selection():
                try:
                    selected_symbols = strategy.select_symbols(
                        self.universe, market_data, portfolio
                    )
                    logger.debug(
                        f"Strategy {strategy.name} selected {len(selected_symbols)} "
                        f"symbols from universe of {len(self.universe)}"
                    )
                except Exception as e:
                    logger.error(f"Symbol selection failed for {strategy.name}: {e}")
                    selected_symbols = self.universe
            else:
                selected_symbols = self.universe

            # Generate signals for selected symbols
            for symbol in selected_symbols:
                bars = market_data.get(symbol)
                if bars is None or bars.empty:
                    continue

                try:
                    signal = strategy.generate_signal(symbol, bars, portfolio)
                    self._process_signal(signal, symbol, portfolio, filled_orders)
                except InsufficientDataError:
                    logger.debug(f"Not enough data for {strategy.name} on {symbol}")
                except Exception as e:
                    logger.error(f"Strategy {strategy.name} error on {symbol}: {e}")

            # Refresh portfolio after processing strategy
            portfolio = self.broker.get_portfolio_state()

        return filled_orders

    def _load_market_data(self) -> dict[str, pd.DataFrame]:
        """Load market data for all symbols in the universe.

        Returns:
            Dict mapping symbol to its OHLCV DataFrame.
        """
        market_data = {}
        for symbol in self.universe:
            try:
                bars = self.data_provider.get_bars(
                    symbol=symbol,
                    timeframe=self.timeframe,
                    limit=self.lookback,
                )
                market_data[symbol] = bars
            except Exception as e:
                logger.error(f"Failed to get data for {symbol}: {e}")
        return market_data

    def _process_signal(
        self,
        signal: TradeSignal,
        symbol: str,
        portfolio: PortfolioState,
        filled_orders: list[FilledOrder],
    ) -> None:
        if signal.signal == Signal.HOLD:
            return

        try:
            price = self.data_provider.get_latest_price(symbol)
        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
            return

        order = self.risk_manager.evaluate_signal(signal, price, portfolio)
        if order is None:
            return

        try:
            filled = self.broker.submit_order(order)
            filled_orders.append(filled)
            logger.info(
                f"Executed: {filled.side.value} {filled.qty} {symbol} "
                f"@ {filled.filled_price:.2f} (strategy={signal.strategy_name})"
            )
        except Exception as e:
            logger.error(f"Order execution failed for {symbol}: {e}")

    def _check_risk_exits(
        self,
        portfolio: PortfolioState,
        filled_orders: list[FilledOrder],
    ) -> None:
        # Update current prices
        for symbol in portfolio.positions:
            try:
                price = self.data_provider.get_latest_price(symbol)
                portfolio.positions[symbol].update_price(price)
            except Exception:
                pass

        # Check stop-loss
        for order in self.risk_manager.check_stop_loss(portfolio):
            try:
                filled = self.broker.submit_order(order)
                filled_orders.append(filled)
            except Exception as e:
                logger.error(f"Stop-loss execution failed: {e}")

        # Check take-profit
        for order in self.risk_manager.check_take_profit(portfolio):
            try:
                filled = self.broker.submit_order(order)
                filled_orders.append(filled)
            except Exception as e:
                logger.error(f"Take-profit execution failed: {e}")

    def get_status(self) -> dict:
        """Get current engine status."""
        portfolio = self.broker.get_portfolio_state()
        return {
            "mode": "live",
            "universe": self.universe,
            "strategies": [s.name for s in self.strategies],
            "cash": portfolio.cash,
            "equity": portfolio.equity,
            "positions": portfolio.position_count,
        }

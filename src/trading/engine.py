from __future__ import annotations

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
    """

    def __init__(
        self,
        data_provider: BaseDataProvider,
        broker: BaseBroker,
        strategies: list[BaseStrategy],
        risk_manager: RiskManager,
        symbols: list[str],
        timeframe: TimeFrame = TimeFrame.DAY_1,
        lookback: int = 100,
    ):
        self.data_provider = data_provider
        self.broker = broker
        self.strategies = strategies
        self.risk_manager = risk_manager
        self.symbols = symbols
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

        # Generate and execute signals for each symbol
        for symbol in self.symbols:
            try:
                bars = self.data_provider.get_bars(
                    symbol=symbol,
                    timeframe=self.timeframe,
                    limit=self.lookback,
                )
            except Exception as e:
                logger.error(f"Failed to get data for {symbol}: {e}")
                continue

            for strategy in self.strategies:
                try:
                    signal = strategy.generate_signal(symbol, bars, portfolio)
                    self._process_signal(signal, symbol, portfolio, filled_orders)
                except InsufficientDataError:
                    logger.debug(f"Not enough data for {strategy.name} on {symbol}")
                except Exception as e:
                    logger.error(f"Strategy {strategy.name} error on {symbol}: {e}")

            # Refresh portfolio after processing symbol
            portfolio = self.broker.get_portfolio_state()

        return filled_orders

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
            "symbols": self.symbols,
            "strategies": [s.name for s in self.strategies],
            "cash": portfolio.cash,
            "equity": portfolio.equity,
            "positions": portfolio.position_count,
        }

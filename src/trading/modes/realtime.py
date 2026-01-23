from __future__ import annotations

import asyncio
from typing import Callable

from loguru import logger

from src.core.models import PortfolioState, TradeSignal
from src.core.types import Signal
from src.trading.engine import TradingEngine

try:
    from alpaca.data.live import StockDataStream
except ImportError:
    StockDataStream = None


class RealtimeTradingMode:
    """Real-time trading mode using Alpaca WebSocket streaming.

    Processes bars as they arrive and executes trades immediately.
    """

    def __init__(
        self,
        engine: TradingEngine,
        api_key: str,
        secret_key: str,
        paper: bool = True,
    ):
        self.engine = engine
        if StockDataStream is None:
            raise ImportError("alpaca-py required for realtime mode")

        base_url = "wss://stream.data.sandbox.alpaca.markets" if paper else None
        self._stream = StockDataStream(api_key, secret_key, raw_data=False)
        self._running = False

    async def _on_bar(self, bar) -> None:
        """Handle incoming bar data."""
        symbol = bar.symbol
        logger.debug(f"Received bar for {symbol}: close={bar.close}")

        try:
            orders = self.engine.run_cycle()
            if orders:
                logger.info(f"Realtime: {len(orders)} orders filled for {symbol}")
        except Exception as e:
            logger.error(f"Realtime processing error for {symbol}: {e}")

    def start(self) -> None:
        """Start real-time streaming and trading."""
        logger.info(f"Starting realtime mode for {self.engine.symbols}")
        self._running = True

        for symbol in self.engine.symbols:
            self._stream.subscribe_bars(self._on_bar, symbol)

        try:
            self._stream.run()
        except KeyboardInterrupt:
            logger.info("Realtime trading stopped by user")
            self.stop()

    def stop(self) -> None:
        """Stop real-time streaming."""
        self._running = False
        try:
            self._stream.stop()
        except Exception:
            pass
        logger.info("Realtime mode stopped")

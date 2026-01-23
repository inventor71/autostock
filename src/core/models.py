from __future__ import annotations

from datetime import datetime

import pandas as pd
from pydantic import BaseModel, Field

from src.core.types import OrderSide, OrderType, Signal


class Bar(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    model_config = {"arbitrary_types_allowed": True}


class TradeSignal(BaseModel):
    symbol: str
    signal: Signal
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    strategy_name: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict)


class Order(BaseModel):
    symbol: str
    side: OrderSide
    qty: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: str = "day"


class FilledOrder(BaseModel):
    order_id: str
    symbol: str
    side: OrderSide
    qty: float
    filled_price: float
    filled_at: datetime
    commission: float = 0.0


class Position(BaseModel):
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    market_value: float = 0.0

    @property
    def cost_basis(self) -> float:
        return self.qty * self.avg_entry_price

    def update_price(self, price: float) -> None:
        self.current_price = price
        self.market_value = self.qty * price
        self.unrealized_pnl = self.market_value - self.cost_basis


class PortfolioState(BaseModel):
    cash: float
    equity: float
    positions: dict[str, Position] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)

    @property
    def total_value(self) -> float:
        return self.cash + sum(p.market_value for p in self.positions.values())

    @property
    def position_count(self) -> int:
        return len(self.positions)


class BacktestResult(BaseModel):
    strategy_name: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return_pct: float
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    equity_curve: list[float] = Field(default_factory=list)
    trades: list[FilledOrder] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

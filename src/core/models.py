from __future__ import annotations

from datetime import datetime

import pandas as pd
from pydantic import BaseModel, Field, model_validator

from src.core.types import OrderClass, OrderSide, OrderType, Signal


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
    sell_pct: float = Field(ge=0.0, le=1.0, default=1.0)  # Sell percentage (1.0 = full position)
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

    # Resting protective legs held at the exchange (BRACKET / OCO). When set,
    # the take-profit leg is a LIMIT and the stop-loss leg is a plain STOP
    # (market-on-touch). Brokers submit these as a single OCO pair so the
    # exchange triggers them on price, gap-safe and without polling.
    order_class: OrderClass = OrderClass.SIMPLE
    take_profit_price: float | None = None
    stop_loss_price: float | None = None

    # F9: Alpaca-shaped extras. ``notional`` is intentionally NOT here — the
    # human-order gate resolves a $ amount to whole shares (qty) up front,
    # mirroring the existing ``/buy SYM N$`` floor, so every Order that reaches
    # a broker carries a concrete qty (avoids Optional-qty churn + fractional
    # bracket legs Alpaca rejects). A trailing stop carries exactly ONE of
    # trail_price / trail_percent.
    trail_price: float | None = None
    trail_percent: float | None = None
    extended_hours: bool = False
    client_order_id: str | None = None

    @model_validator(mode="after")
    def _check_bracket_legs(self) -> "Order":
        if self.order_class in (OrderClass.BRACKET, OrderClass.OCO):
            if self.take_profit_price is None or self.stop_loss_price is None:
                raise ValueError(
                    f"{self.order_class.value} order requires both "
                    f"take_profit_price and stop_loss_price"
                )
        if self.order_type == OrderType.TRAILING_STOP:
            has_price = self.trail_price is not None
            has_pct = self.trail_percent is not None
            if has_price == has_pct:  # both set or neither
                raise ValueError(
                    "trailing_stop requires exactly one of trail_price / trail_percent"
                )
            if has_price and self.trail_price <= 0:
                raise ValueError("trail_price must be > 0")
            if has_pct and not (0 < self.trail_percent < 100):
                raise ValueError("trail_percent must be in (0, 100)")
        elif self.trail_price is not None or self.trail_percent is not None:
            raise ValueError("trail_price/trail_percent only valid for trailing_stop orders")
        return self


class FilledOrder(BaseModel):
    order_id: str
    symbol: str
    side: OrderSide
    qty: float
    filled_price: float
    filled_at: datetime
    commission: float = 0.0


class OpenOrder(BaseModel):
    """A resting (open) order at the broker — used to reconcile protective legs."""

    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    qty: float
    limit_price: float | None = None
    stop_price: float | None = None


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
    # ``equity`` is the single source of truth for account value: the broker
    # sets it authoritatively (Alpaca's account equity; the simulated broker
    # computes cash + Σ market_value). Do not re-add a separate "total_value"
    # that recomputes from ``positions`` — it can silently diverge from the
    # broker's number when position prices are stale.
    cash: float
    equity: float
    positions: dict[str, Position] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)

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

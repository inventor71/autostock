from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from src.agent.journal import Decision


class OHLC(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float


class ExecutionRecord(BaseModel):
    decision_index: int
    symbol: str
    action: str
    order_id: str
    filled_qty: float
    filled_price: float
    ts: str


class RoundTrip(BaseModel):
    symbol: str
    qty: float
    entry_price: float
    exit_price: float
    opened_at: str
    closed_at: str
    realized_pnl: float
    return_pct: float


class DecisionOutcome(BaseModel):
    decision: Decision
    execution: ExecutionRecord | None = None
    round_trip: RoundTrip | None = None
    price_path: list[OHLC] = []
    match_method: Literal["execution_log", "heuristic", "unmatched"] = "unmatched"
    # F62: benchmark-relative (SPY/QQQ) excess return, DIRECTION-AWARE, computed by
    # the collector. Defined only for entry decisions (BUY -> base, SELL_SHORT ->
    # -base); None for exits/HOLD/missing-benchmark. F62 efficacy aggregates on it.
    excess: float | None = None

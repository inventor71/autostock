from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# The conventional key under which the live LLM account's equity series is stored
# and referenced in metrics — kept as a constant so store/runner/metrics agree.
LLM_KEY = "llm"


class EquitySnapshot(BaseModel):
    """One point on a strategy's equity curve — the raw, durable record.

    Source of truth is ``PortfolioState.equity`` (the broker's number). Stored
    one-per-line as JSONL; derived metrics are computed separately so the source
    series can be re-analysed if a formula changes (NFR-4).
    """

    ts: datetime
    strategy: str
    account_masked: str  # NEVER the raw account id / secret (SECURITY / NFR-5)
    equity: float
    cash: float
    position_count: int


class BaselineMetric(BaseModel):
    strategy: str
    cum_return: float
    volatility: float
    max_drawdown: float  # <= 0
    sharpe: float
    n_points: int


class BenchmarkMetrics(BaseModel):
    # Stamped at persist() time, not during compute — compute_metrics must stay
    # pure (identical input → identical output) for reproducible re-analysis (BR-6).
    ts: datetime | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    llm: BaselineMetric | None = None
    baselines: list[BaselineMetric] = Field(default_factory=list)
    # alpha[strategy] = llm.cum_return - baseline.cum_return  (positive = LLM wins)
    alpha: dict[str, float] = Field(default_factory=dict)

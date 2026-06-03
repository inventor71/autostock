"""Domain entities for surge stock detection and analysis."""

from datetime import date as _date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class SurgeCause(str, Enum):
    """Agent-estimated cause of a surge/dive."""

    EARNINGS = "earnings"  # 실적발표
    NEWS = "news"  # 뉴스/공시
    SECTOR = "sector"  # 섹터 동반 상승/하락
    TECHNICAL = "technical"  # 기술적 돌파/붕괴
    AFTER_HOURS = "after_hours"  # 시간외 재료
    MNA = "mna"  # M&A, 지분 이슈
    MACRO = "macro"  # 거시경제/금리/환율
    UNKNOWN = "unknown"  # 원인 파악 불가


class SurgeRecord(BaseModel):
    """A detected surge/dive for a single symbol on a single trading day.

    Written by SurgeDetector to ``workspace/surge/history.jsonl``.
    """

    symbol: str = Field(..., description="Ticker symbol")
    trading_date: _date = Field(..., description="Trading date (YYYY-MM-DD)")
    direction: Literal["up", "down"] = Field(
        ..., description="up = surged, down = dived"
    )
    close_prev: float = Field(..., gt=0, description="Previous close price")
    close_today: float = Field(..., gt=0, description="Today's close price")
    change_pct: float = Field(..., description="Percent change")
    volume: int = Field(..., ge=0, description="Today's volume")
    avg_volume_20d: int = Field(..., ge=0, description="20-day average volume")
    volume_ratio: float = Field(..., ge=0, description="volume / avg_volume_20d")
    high_today: float = Field(..., gt=0, description="Today's high")
    low_today: float = Field(..., gt=0, description="Today's low")
    detected_at: datetime = Field(
        default_factory=datetime.now, description="Detection timestamp (UTC)"
    )


class SurgeAnalysis(BaseModel):
    """Agent root-cause analysis for a surge/dive.

    Written by the agent via the ``surge-analyze`` tool to
    ``workspace/surge/analyses.jsonl``.
    """

    symbol: str = Field(..., description="Ticker symbol — matches SurgeRecord")
    trading_date: _date = Field(..., description="Trading date — matches SurgeRecord")
    estimated_cause: SurgeCause = Field(..., description="Estimated cause category")
    leading_indicators: str = Field(
        ..., description="Signals that preceded the move (free text)"
    )
    information_gap: str = Field(
        ...,
        description="What data would have helped predict this, "
        "that autostock doesn't currently capture (free text)",
    )
    analyzed_at: datetime = Field(
        default_factory=datetime.now, description="Analysis timestamp (UTC)"
    )

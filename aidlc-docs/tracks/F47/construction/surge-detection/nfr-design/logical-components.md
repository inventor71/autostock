# surge-detection — Logical Components

> Minimal Depth | 2026-06-03

## Component Map

```
┌──────────────────────────────────────────────────┐
│                    config/settings.yaml           │
│                    surge: {threshold_pct, ...}    │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│  src/surge/settings.py                            │
│  SurgeDetectionConfig(pydantic BaseModel)         │
│  ─ from_settings() classmethod                    │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│  src/surge/records.py                             │
│  SurgeRecord, SurgeAnalysis, SurgeCause           │
│  ─ pydantic models, validation                    │
└──────────────────────┬───────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
┌────────▼──────────┐    ┌───────────▼───────────┐
│ src/surge/         │    │ src/surge/store.py    │
│ detector.py        │    │ SurgeStore            │
│ SurgeDetector      │    │ ─ write_records()     │
│ ─ scan(universe,   │    │ ─ read_records()      │
│   provider, config)│    │ ─ append_analysis()   │
└────────┬───────────┘    └───────────┬───────────┘
         │                            │
         │                  ┌─────────▼─────────┐
         │                  │ steering/          │
         │                  │ watch_surge/       │
         │                  │ ─ {date}.jsonl     │
         │                  │ ─ {date}-analysis  │
         │                  │   .jsonl           │
         │                  └─────────┬─────────┘
         │                            │
┌────────▼───────────────────────────▼───────────┐
│  src/agent/tools/market.py                      │
│  + surge_list(date=None) -> list[SurgeRecord]   │
│  + surge_analyze(symbol, date, cause,           │
│      leading_indicators, information_gap)       │
│      -> None                                    │
└──────────────────────┬─────────────────────────┘
                       │
┌──────────────────────▼─────────────────────────┐
│  src/agent/tools/__main__.py                    │
│  + "surge-list" subcommand                      │
│  + "surge-analyze" subcommand                   │
└──────────────────────┬─────────────────────────┘
                       │
┌──────────────────────▼─────────────────────────┐
│  src/modes/agent.py                             │
│  + _run_surge_scan() → market close job         │
│  ─ scan → store → continue to EOD review        │
└─────────────────────────────────────────────────┘
```

## Module Details

### LC-1: `src/surge/records.py` (신규)

```python
from pydantic import BaseModel
from enum import Enum
from datetime import date, datetime
from typing import Literal

class SurgeCause(str, Enum):
    EARNINGS = "earnings"
    NEWS = "news"
    SECTOR = "sector"
    TECHNICAL = "technical"
    AFTER_HOURS = "after_hours"
    MNA = "mna"
    MACRO = "macro"
    UNKNOWN = "unknown"

class SurgeRecord(BaseModel):
    symbol: str
    date: date
    direction: Literal["up", "down"]
    close_prev: float
    close_today: float
    change_pct: float
    volume: int
    avg_volume_20d: int
    volume_ratio: float
    high_today: float
    low_today: float
    detected_at: datetime

class SurgeAnalysis(BaseModel):
    symbol: str
    date: date
    estimated_cause: SurgeCause
    leading_indicators: str
    information_gap: str
    analyzed_at: datetime
```

### LC-2: `src/surge/settings.py` (신규)

```python
class SurgeDetectionConfig(BaseModel):
    threshold_pct: float = 7.0
    min_volume: int = 0
    
    @classmethod
    def from_settings(cls, settings: dict) -> "SurgeDetectionConfig":
        return cls(**settings.get("surge", {}))
```

### LC-3: `src/surge/detector.py` (신규)

```python
class SurgeDetector:
    def __init__(self, provider: DataProvider, config: SurgeDetectionConfig):
        ...
    
    def scan(self, universe: list[str], today: date | None = None) -> list[SurgeRecord]:
        ...
    
    def _calculate_change(self, close_today: float, close_prev: float) -> float:
        """Pure function — testable with Hypothesis."""
        return (close_today - close_prev) / close_prev * 100
```

### LC-4: `src/surge/store.py` (신규)

```python
class SurgeStore:
    BASE_DIR = Path("steering/watch_surge")
    
    def write_records(self, records: list[SurgeRecord]) -> int: ...
    def read_records(self, date: date) -> list[SurgeRecord]: ...
    def append_analysis(self, analysis: SurgeAnalysis) -> None: ...
```

### LC-5: `src/agent/tools/market.py` (수정)

기존 파일에 2개 함수 추가:
```python
def surge_list(date_str: str | None = None) -> list[dict]:
    """Read today's surge records. Called via CLI subcommand."""
    ...

def surge_analyze(symbol: str, date_str: str, cause: str,
                  leading_indicators: str, information_gap: str) -> dict:
    """Submit agent analysis. Called via CLI subcommand."""
    ...
```

### LC-6: `src/agent/tools/__main__.py` (수정)

기존 subcommand 목록에 `surge-list`, `surge-analyze` 추가.

### LC-7: `src/modes/agent.py` (수정)

```python
def _run_surge_scan(self):
    """Market-close job: scan universe for surge stocks."""
    if self.surge_detector is None:
        return
    records = self.surge_detector.scan(self.universe)
    written = self.surge_store.write_records(records)
    logger.info(f"surge scan: {len(records)} detected, {written} new")
```

### LC-8: `src/agent/prompts.py` (수정)

`eod_review_prompt()`에 surge 분석 섹션 추가:
```python
def eod_review_prompt(outcomes, quality_summary, surge_count=0):
    ...
    if surge_count > 0:
        lines.append("## Today's Surge Stocks")
        lines.append(f"{surge_count} stocks surged/dived today.")
        lines.append("Run `python -m src.agent.tools surge-list` to see them.")
        lines.append("For each, run `surge-analyze <SYMBOL> <DATE> <CAUSE> \"<LEADING>\" \"<GAP>\"`")
```

### LC-9: `src/data/base.py` (수정)

`DataProvider` 추상 클래스에 `get_daily_bar()` 추가:
```python
@abstractmethod
def get_daily_bar(self, symbol: str, date: date) -> dict | None:
    """Return OHLCV dict for a single trading day."""
```

yfinance/Alpaca provider에 구현 추가.

---

## Thread Safety

- `SurgeDetector.scan()`: EOD job thread에서만 실행 (단일 호출)
- `SurgeStore`: 파일 I/O는 `os.replace()`로 atomic, 동시 쓰기 없음
- Agent tools: subprocess로 실행, daemon context의 steering/ 접근
- 별도 lock 불필요 — 단일 producer (detector) + 단일 analysis producer (agent via tool)

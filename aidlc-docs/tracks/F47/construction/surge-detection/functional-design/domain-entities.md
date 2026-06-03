# surge-detection — Domain Entities

> Functional Design | 2026-06-03

## Entity Overview

```
SurgeRecord (detector 작성)          SurgeAnalysis (agent 작성)
─────────────────────────────        ───────────────────────────
symbol: str                          symbol: str
date: date                           date: date
direction: up | down                 estimated_cause: enum
close_prev: float                    leading_indicators: str
close_today: float                   information_gap: str
change_pct: float                    analyzed_at: datetime
volume: int
avg_volume_20d: int
volume_ratio: float
high_today: float
low_today: float
detected_at: datetime
```

두 엔티티는 `(symbol, date)`로 join된다. 별도 JSONL 파일로 관리:
- `steering/watch_surge/YYYY-MM-DD.jsonl` — SurgeRecord (detector)
- `steering/watch_surge/YYYY-MM-DD-analysis.jsonl` — SurgeAnalysis (agent)

---

## E1: SurgeRecord

급등/급락 감지 결과 레코드. EOD detector가 작성.

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | `str` | 종목 티커 (예: AAPL) |
| `date` | `date` | 거래일 (YYYY-MM-DD) |
| `direction` | `Literal["up", "down"]` | 급등(up) / 급락(down) |
| `close_prev` | `float` | 전일 종가 |
| `close_today` | `float` | 당일 종가 |
| `change_pct` | `float` | 등락률 (%) — up이면 양수, down이면 음수 |
| `volume` | `int` | 당일 거래량 |
| `avg_volume_20d` | `int` | 20거래일 평균 거래량 |
| `volume_ratio` | `float` | 거래량 비율 (`volume / avg_volume_20d`) |
| `high_today` | `float` | 당일 고가 |
| `low_today` | `float` | 당일 저가 |
| `detected_at` | `datetime` | 감지 시각 (ISO 8601, UTC) |

**Identity**: `(symbol, date)` — 동일 거래일에 동일 종목은 1회만 기록 (idempotent).

**Validation**:
- `change_pct` 절대값 ≥ `threshold_pct` (기본 7.0, 설정에서 조정 가능)
- `volume` > 0, `avg_volume_20d` > 0
- `close_prev` > 0, `close_today` > 0

---

## E2: SurgeAnalysis

Agent가 각 급등/급락 종목에 대해 작성하는 원인 분석. `surge-analyze` tool을 통해 steering/에 기록.

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | `str` | 종목 티커 — SurgeRecord와 매칭 |
| `date` | `date` | 거래일 — SurgeRecord와 매칭 |
| `estimated_cause` | `SurgeCause` | 추정 원인 (enum) |
| `leading_indicators` | `str` | 급등 전 감지 가능했을 선행 지표 (자유 텍스트) |
| `information_gap` | `str` | 현재 autostock 데이터로 설명 불가능한 부분 / 수집 희망 데이터 소스 (자유 텍스트) |
| `analyzed_at` | `datetime` | 분석 시각 (ISO 8601, UTC) |

### SurgeCause Enum

```python
class SurgeCause(str, Enum):
    EARNINGS = "earnings"           # 실적발표
    NEWS = "news"                   # 뉴스/공시
    SECTOR = "sector"               # 섹터 동반 상승/하락
    TECHNICAL = "technical"         # 기술적 돌파/붕괴
    AFTER_HOURS = "after_hours"    # 시간외 재료
    MNA = "mna"                     # M&A, 지분 이슈
    MACRO = "macro"                 # 거시경제/금리/환율
    UNKNOWN = "unknown"             # 원인 파악 불가
```

**Validation**:
- `(symbol, date)` pair must exist in the corresponding SurgeRecord file
- `analyzed_at` > `detected_at` (시간 순서 보장)

---

## E3: SurgeDetectionConfig

설정 엔티티 (`config/settings.yaml` → `surge:` 블록).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `threshold_pct` | `float` | `7.0` | 급등/급락 판단 임계값 (%) |
| `min_volume` | `int` | `0` | 최소 거래량 (0 = 제한 없음) |
| `universe` | `list[str] \| None` | `None` | 대상 유니버스 (None = trading.symbols 사용) |

---

## Entity Relationships

```
config/settings.yaml          src/surge/detector.py         steering/watch_surge/
───────────────────          ─────────────────────         ──────────────────────
SurgeDetectionConfig ──► SurgeDetector.scan() ──► YYYY-MM-DD.jsonl
                             │                            (SurgeRecord[])
                             │
                    src/agent/tools/market.py             steering/watch_surge/
                    ─────────────────────────             ──────────────────────
                    surge_list() ◄──── reads ── YYYY-MM-DD.jsonl
                    surge_analyze() ─── writes ──► YYYY-MM-DD-analysis.jsonl
                                                  (SurgeAnalysis[])
```

**Lifecycle**:
1. Market close → `SurgeDetector.scan()` 실행 → `SurgeRecord[]` → `steering/watch_surge/YYYY-MM-DD.jsonl`
2. EOD review turn → agent가 `surge-list` tool 호출 → `SurgeRecord[]` 읽기
3. Agent 분석 → `surge-analyze` tool 호출 → `SurgeAnalysis` → `steering/watch_surge/YYYY-MM-DD-analysis.jsonl`
4. Operator → steering channel read-view로 양쪽 파일 조회 가능

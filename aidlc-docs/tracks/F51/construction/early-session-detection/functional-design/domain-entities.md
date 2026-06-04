# F51 Early-Session Detection — Domain Entities

> **Unit**: `early-session-detection` | **Reference**: F47 `surge-detection/functional-design/domain-entities.md`

## Entity Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    EarlySessionMonitor                        │
│  (진입점 — APScheduler job, 09:30–10:30 ET)                   │
└──────────────────────┬───────────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
┌─────────────┐ ┌────────────┐ ┌──────────────┐
│ BufferManager│ │SignalDetect│ │ WindowDumper  │
│ (E1)         │ │ (E2)       │ │ (E3)          │
└──────┬──────┘ └─────┬──────┘ └──────┬───────┘
       │              │               │
       ▼              ▼               ▼
┌──────────┐  ┌────────────┐  ┌──────────────────┐
│BarRecord │  │SignalEvent  │  │workspace/         │
│(value)   │  │(E4)         │  │  early_session/   │
└──────────┘  └─────┬──────┘  │  {date}/          │
                    │          │  {s}_{t}_{d}.jsonl│
                    ▼          │  _index.jsonl (E5)│
             ┌────────────┐   └──────────────────┘
             │EventIndex   │
             │(E5)         │
             └────────────┘
```

---

## E1: CircularBuffer (순환 버퍼)

종목별 인메모리 순환 버퍼. 정해진 시간窗口(K분)만큼의 BarRecord를 FIFO로 유지.

| Field | Type | Description |
|-------|------|-------------|
| `_buffer` | `dict[str, deque[BarRecord]]` | symbol → bar deque (FIFO) |
| `retention_minutes` | `int` | 유지 시간(분). 기본값 `dump_before_minutes + 5` (여유분). Q2=P=15 → 기본 20분 |
| `symbols` | `list[str]` | 모니터링 대상 심볼 목록 (유니버스) |

**불변식 (Invariants)**:
- `_buffer[symbol]`의 모든 BarRecord는 `now - retention_minutes` 이내의 timestamp를 가진다.
- 가장 오래된 레코드는 deque의 왼쪽(0번 인덱스), 최신은 오른쪽(-1 인덱스).

---

## E2: BarRecord (가격 데이터 1틱)

1회 폴링으로 얻은 단일 시점의 OHLCV 데이터. 버퍼의 기본 단위.

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | `datetime` | UTC (ISO 8601) |
| `symbol` | `str` | 종목 티커 |
| `open` | `float` | 시가 (1분 봉) |
| `high` | `float` | 고가 |
| `low` | `float` | 저가 |
| `close` | `float` | 종가 |
| `volume` | `float` | 거래량 |
| `vwap` | `float \| None` | 거래량가중평균가 (Alpaca 제공 시) |

**제약조건**:
- `close > 0` (가격 유효성)
- `volume >= 0`

---

## E3: SignalDetector (시그널 감지기)

버퍼 데이터를 기반으로 ±X% 이상 움직임을 감지하는 순수 함수 컴포넌트.

| Field | Type | Description |
|-------|------|-------------|
| `threshold_pct` | `float` | 임계값 (기본값 5.0 → ±5%) |
| `window_minutes` | `int` | 감지 시간窗口 (기본값 10분) |
| `min_bars` | `int` | 감지에 필요한 최소 bar 수 (window_minutes와 동일) |

**감지 로직** (순수 함수):
```
detect(bars: list[BarRecord]) → SignalEvent | None
  if len(bars) < min_bars: return None
  first_close = bars[0].close
  last_close = bars[-1].close
  change_pct = (last_close - first_close) / first_close * 100
  if abs(change_pct) >= threshold_pct:
    direction = "surge" if change_pct > 0 else "drop"
    return SignalEvent(...)
  return None
```

---

## E4: SignalEvent (감지된 시그널 이벤트)

감지 트리거 시 생성되는 도메인 이벤트.

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | `str` | 종목 티커 |
| `date` | `date` | 거래일 (YYYY-MM-DD) |
| `detected_at` | `datetime` | 감지 시각 (UTC, ISO 8601) |
| `direction` | `Literal["surge", "drop"]` | 급등/급락 방향 |
| `trigger_pct` | `float` | 감지 트리거 당시 등락률 (%) |
| `trigger_window_min` | `int` | 사용된 시간窗口 (분) |
| `trigger_bars` | `list[BarRecord]` | 감지에 사용된 bar 목록 (window_minutes 분량) |
| `open` | `float` | 당일 시가 |
| `prev_close` | `float` | 전일 종가 |
| `gap_pct` | `float` | 갭률 ((open - prev_close) / prev_close * 100) |

---

## E5: EventIndex (이벤트 인덱스 레코드)

`_index.jsonl` 한 줄. 당일 모든 이벤트의 메타데이터.

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | `str` | 종목 티커 |
| `date` | `str` | 거래일 (YYYY-MM-DD) |
| `detected_at` | `str` | 감지 시각 (ISO 8601) |
| `direction` | `str` | `surge` / `drop` |
| `trigger_pct` | `float` | 감지 트리거 등락률 (%) |
| `trigger_window_min` | `int` | 감지 시간窗口 (분) |
| `open` | `float` | 당일 시가 |
| `prev_close` | `float` | 전일 종가 |
| `gap_pct` | `float` | 갭률 (%) |
| `data_file` | `str` | 덤프된 시계열 파일 상대 경로 |
| `bar_count` | `int` | 덤프된 봉 개수 |
| `time_range_start` | `str` | 덤프 시작 시각 (ISO 8601) |
| `time_range_end` | `str` | 덤프 종료 시각 (ISO 8601) |

---

## E6: DumpWindow (덤프 구간)

감지 시점 기준 전후 구간을 정의하는 값 객체.

| Field | Type | Description |
|-------|------|-------------|
| `before_minutes` | `int` | 감지 전 덤프할 분 (Q2=P=15) |
| `after_minutes` | `int` | 감지 후 계속 수집할 분 (Q2=Q=45) |
| `detected_at` | `datetime` | 기준 시점 (감지 시각) |
| `start` | `datetime` | `detected_at - before_minutes` |
| `end` | `datetime` | `detected_at + after_minutes` |

**제약조건**:
- `end`가 10:30 ET(모니터링 종료)를 초과하면 10:30으로 clamp
- `start`가 09:30 ET(모니터링 시작) 이전이면 09:30으로 clamp

---

## E7: DetectionConfig (감지 설정)

`config/settings.yaml` → `early_session:` 블록에서 로드.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `bool` | `True` | 기능 활성화 여부 |
| `symbols` | `list[str]` | `trading.symbols` | 모니터링 대상 심볼 |
| `threshold_pct` | `float` | `5.0` | 감지 임계값 (Q1=D: ±5%) |
| `window_minutes` | `int` | `10` | 감지 시간窗口 (Q1=D: 10분) |
| `dump_before_minutes` | `int` | `15` | 덤프 전 구간 (Q2=C: 15분) |
| `dump_after_minutes` | `int` | `45` | 덤프 후 구간 (Q2=C: 45분) |
| `poll_interval_seconds` | `int` | `30` | 폴링 간격 (초) |
| `buffer_retention_minutes` | `int` | `20` | 버퍼 유지 시간 (`dump_before + 5`) |
| `monitor_start_et` | `str` | `"09:30"` | 모니터링 시작 (ET) |
| `monitor_end_et` | `str` | `"10:30"` | 모니터링 종료 (ET) |

---

## Entity Relationships

```
DetectionConfig ──1:1──▶ EarlySessionMonitor
                                │
                    ┌───────────┼───────────┐
                    │           │           │
                   1:1         1:1         1:1
                    ▼           ▼           ▼
             BufferManager  SignalDetector  WindowDumper
                    │           │               │
                   1:N          │               │
                    ▼           ▼               ▼
               BarRecord    SignalEvent    workspace/early_session/
                    (E2)        (E4)           {date}/*.jsonl
                                 │
                                1:1
                                 ▼
                            EventIndex (E5)
                          → _index.jsonl
```

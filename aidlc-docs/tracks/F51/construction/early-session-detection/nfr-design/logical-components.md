# F51 Early-Session Detection — Logical Components

> **Unit**: `early-session-detection` | **Depth**: Minimal

## Component Map

```
┌────────────────────────────────────────────────────────┐
│                   데몬 프로세스                           │
│                                                         │
│  ┌──────────────────────────────────────────┐          │
│  │        APScheduler BackgroundScheduler     │          │
│  │  ┌────────────────────────────────────┐   │          │
│  │  │  EarlySessionMonitor (LC1)         │   │          │
│  │  │  tick() every 30s, 09:30-10:30 ET  │   │          │
│  │  └──────────┬─────────────────────────┘   │          │
│  │             │                               │          │
│  │    ┌────────┼────────┬──────────┐          │          │
│  │    ▼        ▼        ▼          ▼          │          │
│  │ ┌──────┐ ┌──────┐ ┌───────┐ ┌────────┐   │          │
│  │ │LC2   │ │LC3   │ │LC4    │ │LC5     │   │          │
│  │ │Buffer│ │Detect│ │Dumper │ │Index   │   │          │
│  │ │Mgr   │ │or    │ │       │ │Writer  │   │          │
│  │ └──┬───┘ └──▲───┘ └───┬───┘ └───┬────┘   │          │
│  │    │        │         │         │         │          │
│  │    │   ┌────┴────┐    │         │         │          │
│  │    │   │ PBT     │    │         │         │          │
│  │    │   │ 대상    │    │         │         │          │
│  │    │   └─────────┘    │         │         │          │
│  └────┼──────────────────┼─────────┼─────────┘          │
│       │                  │         │                     │
│       ▼                  ▼         ▼                     │
│  ┌─────────┐    ┌──────────────────────────┐            │
│  │ LC6     │    │  workspace/early_session/  │            │
│  │ Provider│    │  {date}/                   │            │
│  │ (확장)   │    │  ├── _index.jsonl          │            │
│  └────┬────┘    │  ├── AAPL_094532_drop.jsonl │            │
│       │         │  └── TSLA_095018_surge.jsonl│            │
│       ▼         └──────────────────────────┘            │
│  ┌─────────┐                                             │
│  │ Alpaca  │                                             │
│  │ API     │                                             │
│  └─────────┘                                             │
└────────────────────────────────────────────────────────┘

  ┌──────────────────┐
  │  LC7             │
  │  EarlySession    │
  │  Config          │
  │  (settings.yaml) │
  └──────────────────┘
```

---

## LC1: EarlySessionMonitor (Orchestrator)

| Aspect | Detail |
|--------|--------|
| **역할** | 장초반 1시간 tick 루프 구동, 모든 하위 컴포넌트 조정 |
| **생명주기** | `start()` at 09:30 ET → `tick()` loop → `stop()` at 10:30 ET or last finalize |
| **스레드** | APScheduler job 스레드 1개 (P2: `max_instances=1`) |
| **상태** | `_detected_today: set[str]`, `_pending_finalizes: dict[str, datetime]` |
| **복원** | `start()` 시 `_detected_today = LC5._restore(today)` (P6) |
| **종료** | `now >= monitor_end AND not _pending_finalizes` → `stop()` |

### tick() 실행 순서

```
1. bars_batch = LC6.get_bars(symbols, timeframe=MINUTE_1, limit=2)
2. for sym, bars in bars_batch: LC2.push(sym, bars)
3. for sym in symbols - _detected_today:
     event = LC3.detect(LC2.get_window(sym, window_minutes))
     if event:
       _detected_today.add(sym)
       before = LC2.get_range(sym, start, detected_at)
       LC4.write_before(event, before)
       _pending_finalizes[sym] = now + dump_after_minutes
4. for sym, finalize_at in list(_pending_finalizes):
     if now >= finalize_at:
       after = LC2.get_range(sym, detected_at, now)
       LC4.write_after(event, after)
       LC5.append(event, filepath)
       del _pending_finalizes[sym]
5. if now >= monitor_end and not _pending_finalizes: stop()
```

---

## LC2: BufferManager

| Aspect | Detail |
|--------|--------|
| **모듈** | `src/early_session/buffer.py` |
| **자료구조** | `dict[str, deque[BarRecord]]` |
| **Thread safety** | Lock 없음 (P2: 단일 스레드 전용) |
| **메모리** | ~130 symbols × (retention_minutes ≈ 20) bars × 200 bytes ≈ 520 KB |

### API

```python
class BufferManager:
    def push(self, symbol: str, bar: BarRecord) -> None: ...
    def get_window(self, symbol: str, minutes: int) -> list[BarRecord]: ...
    def get_range(self, symbol: str, start: datetime, end: datetime) -> list[BarRecord]: ...
    def clear(self, symbol: str) -> None: ...
```

---

## LC3: SignalDetector

| Aspect | Detail |
|--------|--------|
| **모듈** | `src/early_session/detector.py` |
| **순수 함수** | ✅ (PBT 대상 — Hypothesis) |
| **Thread safety** | 완전 stateless (순수 함수) |

### API

```python
class SignalDetector:
    def __init__(self, threshold_pct: float, window_minutes: int): ...

    def detect(self, bars: list[BarRecord]) -> SignalEvent | None:
        """순수 함수. bars로부터 SignalEvent 판정."""
        ...
```

---

## LC4: WindowDumper

| Aspect | Detail |
|--------|--------|
| **모듈** | `src/early_session/dumper.py` |
| **I/O** | `workspace/early_session/{date}/` 아래 파일 생성 및 append |
| **원자성** | write_before: 신규 파일. write_after: append. (P3) |

### API

```python
class WindowDumper:
    def __init__(self, workspace_root: Path): ...

    def write_before(self, event: SignalEvent, bars: list[BarRecord]) -> Path:
        """감지 즉시 before 구간 덤프. 새 파일 생성."""
        ...

    def write_after(self, event: SignalEvent, bars: list[BarRecord]) -> Path:
        """Q분 후 after 구간 append. 기존 파일에 추가."""
        ...
```

---

## LC5: IndexWriter

| Aspect | Detail |
|--------|--------|
| **모듈** | `src/early_session/index_writer.py` |
| **I/O** | `workspace/early_session/{date}/_index.jsonl` |
| **원자성** | `os.replace()` (P3) |

### API

```python
class IndexWriter:
    def __init__(self, workspace_root: Path): ...

    def append(self, event: SignalEvent, data_file: Path, bar_count: int,
               time_start: datetime, time_end: datetime) -> None: ...

    def read_detected(self, date: str) -> set[str]:
        """인덱스에서 이미 감지된 심볼 복원 (P6)."""
        ...
```

---

## LC6: DataProvider Extension

| Aspect | Detail |
|--------|--------|
| **모듈** | `src/data/base.py`, `src/data/providers/alpaca_provider.py` |
| **변경** | `get_bars(symbol: str)` → `get_bars(symbol: str \| list[str])` |
| **하위 호환** | `str` 전달 시 기존 동일 동작 |

### 변경 API

```python
# BaseDataProvider (base.py)
def get_bars(
    self,
    symbol: str | list[str],
    timeframe: TimeFrame = TimeFrame.DAY_1,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 100,
) -> pd.DataFrame | dict[str, pd.DataFrame]:  # str→DataFrame, list→dict
    ...

# AlpacaDataProvider (alpaca_provider.py)
def get_bars(self, symbol, ...):
    request = StockBarsRequest(symbol_or_symbols=symbol, ...)
    df = self._client.get_stock_bars(request)
    if isinstance(symbol, list):
        # multi-index → dict
        return {sym: group.droplevel("symbol") for sym, group in df.groupby("symbol")}
    else:
        # 기존 단일심볼 동작
        return df.droplevel("symbol")
```

---

## LC7: EarlySessionConfig

| Aspect | Detail |
|--------|--------|
| **모듈** | `src/early_session/config.py` (또는 `config/settings.py` 확장) |
| **프레임워크** | pydantic `BaseSettings` |
| **소스** | `config/settings.yaml` → `early_session:` 블록 |

### 스키마

```python
class EarlySessionConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EARLY_SESSION_")

    enabled: bool = True
    threshold_pct: float = 5.0
    window_minutes: int = 10
    dump_before_minutes: int = 15
    dump_after_minutes: int = 45
    poll_interval_seconds: int = 30
    buffer_retention_minutes: int = 20
    monitor_start_et: str = "09:30"
    monitor_end_et: str = "10:30"
```

---

## Component Interaction Table (Thread Safety)

| Component | Thread(s) | Shared State | Safety Mechanism |
|-----------|-----------|--------------|------------------|
| LC1 Monitor | APScheduler job 1개 | `_detected_today`, `_pending_finalizes` | `max_instances=1` (P2) |
| LC2 BufferManager | Monitor 스레드 전용 | `_buffer: dict[str, deque]` | 단일 스레드 (P2) |
| LC3 SignalDetector | Monitor 스레드 (호출) | 없음 (stateless) | 순수 함수 |
| LC4 WindowDumper | Monitor 스레드 | 없음 (I/O only) | 파일시스템 |
| LC5 IndexWriter | Monitor 스레드 | 없음 (I/O only) | `os.replace()` |
| LC6 Provider | Monitor 스레드 | 없음 (API call) | Stateless |
| LC7 Config | 읽기 전용 | 불변 | 생성자 주입 |

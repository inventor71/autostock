# F51 Early-Session Detection — Business Logic Model

> **Unit**: `early-session-detection`

## Overall Flow

```
                    ┌─────────────────────────────────────┐
                    │        APScheduler (데몬 내)          │
                    │  market_open job → start_monitoring  │
                    │  09:30 ET trigger                     │
                    └──────────────┬──────────────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────────────┐
                    │       EarlySessionMonitor            │
                    │  (09:30–10:30 ET 동안 poll_interval  │
                    │   간격으로 tick() 실행)               │
                    └──────────────┬──────────────────────┘
                                   │
                          ┌────────┴────────┐
                          ▼                 ▼
                ┌──────────────┐   ┌────────────────┐
                │ 1. fetch()   │   │ 4. finalize()   │
                │ (multi-symbol│   │ (Q분 후 덤프     │
                │  get_bars)   │   │  완료 + 정리)   │
                └──────┬───────┘   └────────────────┘
                       │
                       ▼
                ┌──────────────┐
                │ 2. buffer()  │
                │ (FIFO push,  │
                │  old pop)    │
                └──────┬───────┘
                       │
                       ▼
                ┌──────────────┐
                │ 3. detect()  │
                │ (buffer →    │
                │  SignalEvent │
                │  or None)    │
                └──────┬───────┘
                       │
                  SignalEvent?
                       │
              ┌────────┴────────┐
              │ YES             │ NO → 다음 tick
              ▼                 │
       ┌──────────────┐         │
       │ 3a. dump()   │         │
       │ (전 구간 덤프  │         │
       │  + index 추가)│         │
       └──────┬───────┘         │
              │                 │
              ▼                 │
       ┌──────────────┐         │
       │ 3b. schedule │         │
       │ _finalize()  │         │
       │ (Q분 후)      │         │
       └──────────────┘         │
                                │
              ┌─────────────────┘
              │
              ▼
       다음 tick (poll_interval 후)
```

---

## BLM-1: EarlySessionMonitor (진입점)

**책임**: 장초반 1시간 동안 tick 루프를 구동하는 최상위 오케스트레이터.

**생명주기**:
1. `start()` — 09:30 ET, APScheduler market-open job에 의해 호출
2. `tick()` 루프 — `poll_interval_seconds`(30초) 간격으로 실행
3. `stop()` — 10:30 ET 도달 또는 모든 pending finalize 완료 시

**Pseudo-code**:
```python
class EarlySessionMonitor:
    def __init__(self, config: DetectionConfig, data_provider, workspace_root: Path):
        self.config = config
        self.buffer = BufferManager(config)
        self.detector = SignalDetector(config)
        self.dumper = WindowDumper(config, workspace_root)
        self.index_writer = IndexWriter(workspace_root)
        self._detected_today: set[str] = set()  # idempotency (Q3=A)
        self._pending_finalizes: dict[str, datetime] = {}  # symbol → finalize_at

    def tick(self):
        now = datetime.now(UTC)
        # 1. Fetch
        bars_batch = self.data_provider.get_bars(
            self.config.symbols,
            timeframe=TimeFrame.MINUTE_1,
            limit=2  # 최근 2개 봉 (30초 폴링이므로 보통 1개 신규)
        )
        # 2. Buffer
        for symbol, bars in bars_batch.items():
            for bar in bars:
                self.buffer.push(symbol, BarRecord.from_bar(bar))
        # 3. Detect (이미 감지된 심볼은 스킵)
        for symbol in self.config.symbols:
            if symbol in self._detected_today:
                continue
            bars = self.buffer.get_window(symbol, self.config.window_minutes)
            event = self.detector.detect(bars)
            if event:
                self._detected_today.add(symbol)
                # 3a. Dump before-window
                before_bars = self.buffer.get_range(
                    symbol, event.detected_at - timedelta(minutes=self.config.dump_before_minutes),
                    event.detected_at
                )
                self.dumper.write_before(event, before_bars)
                # 3b. Schedule finalize
                finalize_at = now + timedelta(minutes=self.config.dump_after_minutes)
                self._pending_finalizes[symbol] = finalize_at
        # 4. Finalize 완료된 것 처리
        for symbol, finalize_at in list(self._pending_finalizes.items()):
            if now >= finalize_at:
                after_bars = self.buffer.get_range(
                    symbol, event.detected_at, now
                )
                data_file = self.dumper.write_after(event, after_bars)
                self.index_writer.append(event, data_file)
                del self._pending_finalizes[symbol]
        # 5. 종료 체크
        if now >= self.monitor_end and not self._pending_finalizes:
            self.stop()
```

**재시작 안전성**: 데몬 재시작 시 `_detected_today`는 `workspace/early_session/{today}/_index.jsonl`을 읽어 복원한다.

---

## BLM-2: BufferManager (버퍼 관리)

**책임**: 종목별 CircularBuffer 유지. FIFO push + 범위 조회.

**핵심 동작**:

```
push(symbol, bar):
  self._buffer[symbol].append(bar)
  # 오래된 데이터 제거 (FIFO)
  cutoff = now - retention_minutes
  while self._buffer[symbol][0].timestamp < cutoff:
      self._buffer[symbol].popleft()

get_window(symbol, minutes) → list[BarRecord]:
  cutoff = now - timedelta(minutes=minutes)
  return [b for b in self._buffer[symbol] if b.timestamp >= cutoff]

get_range(symbol, start, end) → list[BarRecord]:
  return [b for b in self._buffer[symbol] if start <= b.timestamp <= end]
```

**스레드 안전성**: 단일 스레드에서만 접근 (APScheduler job 스레드). Lock 불필요.

---

## BLM-3: SignalDetector (감지 로직)

**책임**: 주어진 bar 윈도우에서 ±threshold_pct% 이상 움직임 탐지. **순수 함수** (PBT 대상).

**알고리즘**:
```
detect(bars: list[BarRecord]) → SignalEvent | None:
  if len(bars) < min_bars(10):  # window_minutes=10, 최소 10개 bar
    return None
  # rolling window: bars[0..N] 중 first_close→last_close 변화율 계산
  first = bars[0]
  last = bars[-1]
  change = (last.close - first.close) / first.close * 100
  if abs(change) < threshold_pct(5.0):
    return None
  direction = "surge" if change > 0 else "drop"
  return SignalEvent(
    symbol=first.symbol,
    detected_at=last.timestamp,
    direction=direction,
    trigger_pct=round(change, 2),
    trigger_window_min=window_minutes,
    trigger_bars=bars,
    ...
  )
```

**설계 결정**: `close-to-close` 기준 사용 (low-to-high나 open-to-close가 아닌). 가장 단순하고 일관된 측정.

---

## BLM-4: WindowDumper (시계열 덤프)

**책임**: 감지 이벤트의 시계열 데이터를 `workspace/early_session/{date}/` 에 개별 파일로 기록.

**파일 네이밍**: `{symbol}_{HHMMSS}_{direction}.jsonl`
- 예: `AAPL_094532_drop.jsonl`

**파일 형식** (JSONL, 한 줄이 하나의 bar):
```jsonl
{"t":"2026-06-03T09:30:00Z","o":195.50,"h":195.80,"l":194.20,"c":194.50,"v":125000,"vw":195.10}
{"t":"2026-06-03T09:31:00Z","o":194.50,"h":194.90,"l":193.10,"c":193.50,"v":250000,"vw":193.80}
```

**두 단계 쓰기**:
1. `write_before(event, bars)` — 감지 즉시 before 구간 기록. 파일 생성.
2. `write_after(event, bars)` — Q분 후 after 구간 append. 파일 완성.

**구현**:
```
write_before(event, bars):
  filepath = workspace_root / event.date / f"{event.symbol}_{event.detected_at:%H%M%S}_{event.direction}.jsonl"
  os.makedirs(filepath.parent, exist_ok=True)
  with open(filepath, "w") as f:
    for bar in bars:
      f.write(bar_to_jsonl(bar) + "\n")
  return filepath

write_after(event, bars):
  filepath = resolve_existing_path(event)  # write_before에서 생성된 파일
  with open(filepath, "a") as f:
    for bar in bars:
      f.write(bar_to_jsonl(bar) + "\n")
  return filepath
```

**원자성**: `write_before`는 신규 파일 생성이므로 손상 위험 없음. `write_after`는 기존 파일에 append — 도중 크래시 시 마지막 라인이 불완전할 수 있으나, JSONL 특성상 완전한 라인까지만 읽으면 복구 가능.

---

## BLM-5: IndexWriter (이벤트 인덱스)

**책임**: `_index.jsonl`에 완료된 이벤트의 메타데이터 append.

**구현**:
```
append(event, data_file):
  index_path = workspace_root / event.date / "_index.jsonl"
  record = EventIndex(
    symbol=event.symbol,
    date=str(event.date),
    detected_at=event.detected_at.isoformat(),
    direction=event.direction,
    trigger_pct=event.trigger_pct,
    trigger_window_min=event.trigger_window_min,
    data_file=str(data_file.relative_to(workspace_root)),
    bar_count=(before_count + after_count),
    time_range_start=...,
    time_range_end=...,
  )
  atomic_append_jsonl(index_path, record)
```

**원자성**: `os.replace()`를 사용한 atomic write.

---

## BLM-6: Provider 확장 (다중심볼 get_bars)

기존 `BaseDataProvider.get_bars(symbol: str, ...)` → `get_bars(symbol: str | list[str], ...)` 시그니처 확장 (Q5=A).

**변경 포인트**:
- `BaseDataProvider.get_bars()` — 시그니처 확장, 기본 구현은 단일심볼만 지원 (list 전달 시 `NotImplementedError` → 하위 클래스에서 오버라이드)
- `AlpacaDataProvider.get_bars()` — Alpaca SDK의 `symbol_or_symbols: list[str]` 지원 활용. multi-index DataFrame 처리: symbol → DataFrame 매핑 dict 반환
- 기존 호출부: `get_bars("AAPL", ...)` — 호환성 유지 (`str`은 그대로 단일심볼)

**반환 타입**:
- `symbol: str` → `pd.DataFrame` (기존 동작 유지)
- `symbol: list[str]` → `dict[str, pd.DataFrame]` (symbol → bars 매핑)

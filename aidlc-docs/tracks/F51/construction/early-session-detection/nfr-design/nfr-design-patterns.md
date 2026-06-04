# F51 Early-Session Detection — NFR Design Patterns

> **Unit**: `early-session-detection` | **Depth**: Minimal | **Reference**: F47, F3 NFR Design

## Pattern Summary

| # | Pattern | Source | Applies to |
|---|---------|--------|------------|
| P1 | Cache-vs-Detect Separation | F3 (WakeDetector) | BufferManager ↔ SignalDetector |
| P2 | APScheduler Single-Thread | F3 | EarlySessionMonitor.tick() |
| P3 | Atomic File Writes | F47 (surge) | IndexWriter, WindowDumper |
| P4 | Fail-Closed per Symbol | F47 (surge) | fetch error isolation |
| P5 | Config-Driven Parameters | F1, F47 | DetectionConfig (pydantic) |
| P6 | Index-Based State Recovery | F3 (fired-set) | _detected_today 복원 |

---

## P1: Cache-vs-Detect Separation

**문제**: 감지 tick이 네트워크 I/O(get_bars)와 감지 로직을 같은 스레드에서 실행하면, 네트워크 지연이 감지 레이턴시에 직결되고 scheduler tick이 overrun 된다.

**해결**: F3 `WakeDetector`에서 검증된 패턴 — fetch와 detect를 분리.

```
tick():
  1. fetch() — Alpaca API 호출 (네트워크 I/O, ~5s). 결과를 BufferManager에 push.
  2. detect() — 인메모리 버퍼에서 순수 함수 호출 (네트워크 없음, ~ms).
```

**적용**:
- `SignalDetector.detect(bars)`는 **순수 함수**. 네트워크 호출, 파일 I/O, 글로벌 상태 접근 없음.
- BufferManager는 단순 `collections.deque` 래퍼. lock 불필요 (단일 스레드).
- tick() 전체가 하나의 APScheduler job 스레드에서 실행 → `coalesce=True` 적용.

**PBT 영향**: `SignalDetector.detect()`가 순수 함수이므로 Hypothesis로 속성 기반 테스트 가능 (PBT-03).

---

## P2: APScheduler Single-Thread + Coalesce

**문제**: 30초 간격의 tick이 때때로 30초를 초과하면(예: 네트워크 스파이크), 이전 tick이 끝나기 전에 다음 tick이 트리거되어 중복 실행될 수 있다.

**해결**: F3의 `WakeDetector`와 동일한 구성.

```python
scheduler.add_job(
    monitor.tick,
    trigger="interval",
    seconds=config.poll_interval_seconds,  # 30
    coalesce=True,           # 이전 tick이 아직 실행 중이면 다음 tick skip
    misfire_grace_time=30,   # 최대 30초 지연 허용
    max_instances=1,          # 동시 실행 1개로 제한
)
```

**적용**:
- `max_instances=1`: tick()이 동시에 2개 이상 실행되지 않음.
- `coalesce=True`: tick이 30초보다 오래 걸리면 쌓인 스케줄을 하나로 병합.
- BufferManager, SignalDetector, WindowDumper 모두 단일 스레드에서만 접근 → **thread-safe by construction, lock 불필요**.

---

## P3: Atomic File Writes

**문제**: 파일 쓰기 도중 데몬 크래시나 정전이 발생하면 데이터가 손상될 수 있다.

**해결**:

| 파일 | 방식 | 원자성 |
|------|------|--------|
| 덤프 `{s}_{t}_{d}.jsonl` | `write_before`: 신규 파일 생성. `write_after`: append. | 완전한 JSONL 라인 단위 복구 가능. 마지막 불완전 라인은 무시. |
| 인덱스 `_index.jsonl` | 임시 파일에 쓰기 → `os.replace(tmp, target)` | 원자적 교체. 부분 쓰기 없음. |

**적용**:
- F47 surge detection의 `atomic_append_jsonl` 패턴 재사용.
- `IndexWriter.append()`: pydantic model → dict → JSON line → tempfile → `os.replace()`.
- 복구: JSONL reader는 마지막 줄이 불완전하면(`json.loads` 실패) 해당 라인만 스킵.

---

## P4: Fail-Closed per Symbol

**문제**: 유니버스 내 한 종목의 데이터 조회 실패가 전체 모니터링을 중단시켜서는 안 된다.

**해결**: F47 surge detection의 격리 패턴.

```
try:
    bars = provider.get_bars(symbols, ...)
except Exception as e:
    logger.warning(f"Batch fetch failed: {e}")
    return  # tick skip, next tick retry

# per-symbol errors are inside the batch:
for symbol, df in bars.items():
    if df.empty:
        continue  # no data for this symbol
    buffer.push(symbol, BarRecord.from_bar(row))
```

**적용**:
- 다중심볼 `get_bars`가 배치로 요청하므로 개별 종목 실패보다는 전체 배치 실패만 가능.
- 배치 실패 → tick skip, 로그. 다음 tick(30초 후) 재시도 (BR-8.2).
- Alpaca SDK가 부분 응답을 지원하는 경우(df에 포함된 종목만 처리), 미지원 시 전체 배치 실패로 처리.

---

## P5: Config-Driven Parameters

**문제**: 감지 임계값, 덤프 윈도우 등을 튜닝할 때마다 코드를 수정해야 하면 운영 부담.

**해결**: `settings.yaml` → pydantic `BaseSettings` → `DetectionConfig` 주입.

```yaml
early_session:
  enabled: true
  threshold_pct: 5.0
  window_minutes: 10
  dump_before_minutes: 15
  dump_after_minutes: 45
  poll_interval_seconds: 30
```

```python
class EarlySessionConfig(BaseSettings):
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

**적용**: F1 `IntradayConfig`, F47 `SurgeConfig`와 동일 패턴. `config/settings.py`에 `EarlySessionConfig` 추가.

---

## P6: Index-Based State Recovery

**문제**: 데몬 재시작 시 어떤 종목이 이미 감지되었는지 알아야 중복 감지를 방지할 수 있다.

**해결**: F3 `fired_set` 패턴. `_index.jsonl`을 읽어 `_detected_today`를 복원.

```python
def _restore_detected(self, date: str) -> set[str]:
    index_path = self.workspace_root / date / "_index.jsonl"
    if not index_path.exists():
        return set()
    detected = set()
    for line in read_jsonl_lines(index_path):
        record = json.loads(line)
        detected.add(record["symbol"])
    return detected
```

**적용**:
- `EarlySessionMonitor.__init__()`에서 `_detected_today = _restore_detected(today)`.
- 버퍼는 휘발성(인메모리)이므로 재시작 시 소실. 허용 가능한 trade-off (NFR-RE-1).
- 이미 덤프 완료된 이벤트는 디스크에 보존됨.

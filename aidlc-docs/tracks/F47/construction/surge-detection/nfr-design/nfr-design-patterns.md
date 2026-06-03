# surge-detection — NFR Design Patterns

> Minimal Depth | 2026-06-03

---

## P1: Atomic File Write

**Pattern**: temp file write → `os.replace()` (stdlib atomic rename)

```
write path: steering/watch_surge/{date}.jsonl.tmp.{pid}.{uuid}
final path: steering/watch_surge/{date}.jsonl
```

- `os.replace()`는 POSIX에서 atomic — consumer가 부분 파일을 볼 수 없음
- 실패 시 tmp 파일 정리 (`try/finally`)
- 기존 `src/agent/steering/jsonl.py::atomic_write_text()` 재사용

**적용 위치**: `SurgeStore.write_records()`, `SurgeStore.append_analysis()`

---

## P2: Fail-Isolated Iterator

**Pattern**: per-item try/except, 개별 실패를 로깅하고 계속 진행

```python
for symbol in universe:
    try:
        result = process_one(symbol)
        if result:
            results.append(result)
    except ExpectedError:
        logger.warning(...)
    except Exception:
        logger.exception(...)
```

- 한 종목의 데이터 누락/API 오류가 전체 scan을 중단하지 않음
- 결과는 부분 성공 (일부 종목만 기록됨)

**적용 위치**: `SurgeDetector.scan()`

---

## P3: Torn-Line Safe JSONL Reader

**Pattern**: 라인 단위 읽기, 마지막 불완전 라인은 무시

```python
def read_complete_lines(path: Path) -> list[str]:
    text = path.read_text()
    lines = text.splitlines()
    # 마지막 라인이 완전한 JSON이 아니면 버림
    if lines and not is_valid_json(lines[-1]):
        lines.pop()
    return lines
```

- Writer가 crash 되어도 reader는 항상 valid JSON 라인만 반환
- 기존 `src/agent/steering/jsonl.py::read_complete_lines()` 재사용

**적용 위치**: `SurgeStore.read_records()`

---

## P4: Agent Tool CLI Convention

**Pattern**: `python -m src.agent.tools <cmd> [args...]` → stdout JSON

```python
# __main__.py
def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="cmd")
    
    # surge-list
    p = subparsers.add_parser("surge-list")
    p.add_argument("--date", type=str, default=None)
    
    # surge-analyze
    p = subparsers.add_parser("surge-analyze")
    p.add_argument("symbol")
    p.add_argument("date")
    p.add_argument("cause")
    p.add_argument("leading_indicators")
    p.add_argument("information_gap")
    
    args = parser.parse_args()
    result = dispatch(args)
    print(json.dumps(result))
```

- 일관된 CLI + JSON stdout 패턴
- 기존 `src/agent/tools/__main__.py` 구조 따름

**적용 위치**: `src/agent/tools/market.py`, `src/agent/tools/__main__.py`

---

## P5: EOD Market-Close Job

**Pattern**: APScheduler market_close trigger → surge scan → EOD review

```python
# modes/agent.py
scheduler.add_market_close_job(
    _run_surge_scan_and_eod,
    job_id="surge_scan",
)
```

- 기존 `add_market_close_job` 재사용
- scan 실패해도 EOD review turn은 정상 진행 (BR-7.2)

**적용 위치**: `modes/agent.py`

---

## P6: Idempotent Append

**Pattern**: 쓰기 전 기존 데이터 읽기 → 중복 필터링 → 신규 건만 append

```python
def write_records(records: list[SurgeRecord]) -> int:
    existing = {r.symbol for r in read_records(records[0].date)}
    new_records = [r for r in records if r.symbol not in existing]
    if new_records:
        append_lines(path, [r.model_dump_json() for r in new_records])
    return len(new_records)
```

- 동일 (date, symbol) 재실행에도 중복 없음
- 분석(append_analysis)은 중복 필터링 없이 항상 append (최신 분석이 우선)

**적용 위치**: `SurgeStore.write_records()`

---

## Pattern Summary

| Pattern | Source | New/Reuse |
|---------|--------|-----------|
| P1 Atomic Write | `steering/jsonl.py::atomic_write_text()` | Reuse |
| P2 Fail-Isolated Iterator | 신규 구현 | New |
| P3 Torn-Line Reader | `steering/jsonl.py::read_complete_lines()` | Reuse |
| P4 Agent Tool CLI | `agent/tools/__main__.py` 패턴 | New (패턴 재사용) |
| P5 EOD Market-Close Job | `modes/agent.py` scheduler | New (job 추가) |
| P6 Idempotent Append | 신규 구현 | New |

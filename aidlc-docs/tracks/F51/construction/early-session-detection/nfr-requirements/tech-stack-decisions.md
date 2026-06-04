# F51 Early-Session Detection — Tech Stack Decisions

> **Unit**: `early-session-detection` | **Depth**: Minimal

## Decision Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Runtime deps** | **0 new** | stdlib + 기존 pydantic, APScheduler, loguru, alpaca-py |
| **Dev deps** | **0 new** | Hypothesis (PBT Partial, 이미 설치됨) |
| **New packages** | 없음 | `pyproject.toml` 변경 없음 |
| **Python version** | 3.11+ (기존) | 프로젝트 표준 |

---

## 1. 데이터 조회

### Provider: AlpacaDataProvider (기존)

기존 `get_bars(symbol, timeframe, limit)` 를 `get_bars(symbol: str | list[str], ...)` 로 확장.

**Alpaca SDK 지원 검증**:
- `StockBarsRequest(symbol_or_symbols: str | list[str])` — 다중심볼 네이티브 지원.
- 다중심볼 시 multi-index DataFrame `(symbol, timestamp)` 반환 → `groupby("symbol")`로 dict로 변환.
- IEX feed (무료 티어) 기준 1분 봉 제공. 딜레이 15분 → 실시간 감지에 충분.

**변경 범위**:
- `src/data/base.py` — `get_bars()` 시그니처 `str | list[str]`로 확장, 기본 구현은 list 전달 시 `NotImplementedError`
- `src/data/providers/alpaca_provider.py` — list 처리 구현 (multi-index → dict), 단일심볼 기존 동작 유지
- 기존 호출부 변경 없음 (`str` 전달 시 완전한 하위 호환)

---

## 2. 스케줄링

### APScheduler (기존)

데몬 내 `BackgroundScheduler`에 job 추가:
```python
scheduler.add_job(
    monitor.tick,
    trigger="cron",
    day_of_week="mon-fri",
    hour=9, minute=30,  # 09:30 ET
    end_date=None,
    misfire_grace_time=30,
    coalesce=True,
)
```

- `coalesce=True`: tick이 폴링 간격보다 오래 걸리면 쌓인 실행을 병합 (F3 패턴 재사용).
- `misfire_grace_time=30`: 최대 30초 지연 허용.
- 종료는 `monitor.stop()`에서 job 제거 또는 10:30 도달 시 자체 종료.

**09:30 트리거 방식**: F3의 `WakeDetector`가 APScheduler `market_open` job으로 시작하는 것과 동일한 패턴. `modes/agent.py`의 시장 오픈 감지 루틴에서 `monitor.start()` 호출.

---

## 3. 데이터 저장

### JSONL (stdlib `json` + `os.replace`)

- 덤프 파일: `workspace/early_session/{date}/{symbol}_{HHMMSS}_{direction}.jsonl`
- 인덱스: `workspace/early_session/{date}/_index.jsonl`
- 라인 단위 append-only. 신규 의존성 없음.
- F47 surge detection과 동일한 패턴.

---

## 4. 설정

### `config/settings.yaml` → `early_session:` 블록

```yaml
early_session:
  enabled: true
  threshold_pct: 5.0        # ±5%
  window_minutes: 10         # 10분 내
  dump_before_minutes: 15    # 감지 전 15분
  dump_after_minutes: 45     # 감지 후 45분
  poll_interval_seconds: 30  # 30초 폴링
  buffer_retention_minutes: 20
  monitor_start_et: "09:30"
  monitor_end_et: "10:30"
```

pydantic `BaseSettings` 로드 (기존 `config.py` 패턴 재사용).

---

## 5. 데이터 모델

### pydantic (기존)

- `BarRecord`, `SignalEvent`, `EventIndex` — pydantic `BaseModel`.
- JSONL 직렬화: `.model_dump(mode="json")` + `json.dumps()`.
- F47과 동일한 패턴.

---

## 6. CLI 인스펙션 (Optional)

### stdlib `argparse`

- `python -m early_session inspect --date 2026-06-03` — 당일 이벤트 목록 + 시계열 미리보기.
- 별도 CLI 프레임워크 불필요. F1 `intraday_collector.py` CLI 패턴 재사용.

---

## 7. 검증

| 항목 | 도구 | 비고 |
|------|------|------|
| **단위 테스트** | pytest (기존) | `tests/test_early_session.py` |
| **PBT** | Hypothesis (기존) | 순수 함수 + serialization round-trip |
| **Type check** | pyright (기존) | strict mode |
| **Live verify (R1)** | 알파카 페이퍼 계정 | 다중심볼 `get_bars` 실제 호출 검증 |
| **회귀 테스트** | pytest (기존) | 전체 스위트 통과 확인 |

---

## 결론

**0 new runtime dependencies. 0 new dev dependencies.**
완전히 기존 스택(stdlib + pydantic + APScheduler + alpaca-py + Hypothesis)에서 모든 요구사항 충족 가능.
F47과 동일한 결론.

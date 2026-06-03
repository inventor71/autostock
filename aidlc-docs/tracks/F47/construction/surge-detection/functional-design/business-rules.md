# surge-detection — Business Rules

> Functional Design | 2026-06-03

## BR-1: 급등/급락 판단 규칙

### BR-1.1: 임계값 기준
- `abs(change_pct) >= surge.threshold_pct` → 급등/급락으로 분류
- `change_pct > 0` → `direction = "up"` (급등)
- `change_pct < 0` → `direction = "down"` (급락)
- 기본 `threshold_pct = 7.0`, `config/settings.yaml`에서 조정 가능

### BR-1.2: 등락률 계산
- `change_pct = (close_today - close_prev) / close_prev * 100`
- `close_prev`: 직전 거래일 종가 (주말/휴일 건너뛰기)
- `close_today`: 당일 정규장 종가
- 가격은 split/dividend adjusted 사용

### BR-1.3: 결측 데이터
- `close_prev` 또는 `close_today` 조회 실패 → 해당 종목 skip (로그만 남김)
- `volume` 또는 `avg_volume_20d` 조회 실패 → 0으로 기록하고 진행 (필수 필드 아님)

---

## BR-2: Idempotency 규칙

### BR-2.1: 중복 감지 방지
- `(symbol, date)` 기준으로 동일 거래일 동일 종목은 1번만 기록
- `SurgeStore.write_records()`에서 기존 파일 읽어 중복 체크

### BR-2.2: 분석 중복 처리
- `SurgeAnalysis`는 append-only — 동일 (symbol, date)에 대해 여러 번 분석 가능
- Consumer는 `(symbol, date)` 당 가장 최근 `analyzed_at`을 사용

---

## BR-3: Agent 분석 규칙

### BR-3.1: 분석 대상
- Agent는 `surge-list`로 조회된 모든 급등/급락 종목에 대해 분석을 시도해야 함
- 정보 부족으로 분석이 어려운 경우 `estimated_cause = "unknown"`으로 기록

### BR-3.2: 분석 가이드 (프롬프트)
Agent EOD review 시 surge 분석 섹션 추가:
```
## Today's Surge Stocks
Run `python -m src.agent.tools surge-list` to see today's surge/dive stocks.
For EACH stock, run `python -m src.agent.tools surge-analyze <SYMBOL> <DATE> <CAUSE> "<LEADING_INDICATORS>" "<INFORMATION_GAP>"` where:
- CAUSE: earnings | news | sector | technical | after_hours | mna | macro | unknown
- LEADING_INDICATORS: What signals (if any) preceded this move that autostock could have detected?
- INFORMATION_GAP: What data would have helped predict this, that autostock doesn't currently capture?
```

### BR-3.3: 분석 검증
- `surge-analyze` tool은 제출된 `(symbol, date)`가 당일 SurgeRecord에 존재하는지 검증
- 존재하지 않으면 에러 반환 (agent가 없는 종목을 분석하려는 것)

---

## BR-4: 파일 무결성 규칙

### BR-4.1: Atomic Write
- 모든 JSONL 쓰기는 temp file write → `os.replace()` 패턴 사용
- 부분 작성된 파일이 consumer에게 노출되지 않음

### BR-4.2: Append-Only
- 기존 레코드는 수정하지 않고 append만 수행
- 파일 손상 시 마지막 라인까지 복구 가능 (torn-line guard)

### BR-4.3: Torn-Line Guard
- JSONL 읽기 시 마지막 라인이 완전한 JSON이 아니면 무시
- 기존 `src/agent/steering/jsonl.py`의 `read_complete_lines()` 재사용

---

## BR-5: Fail-Isolation 규칙

### BR-5.1: Per-Symbol Isolation
- 개별 종목의 데이터 조회 실패는 전체 scan을 중단하지 않음
- 실패한 종목은 warning 로그 + skip

### BR-5.2: Empty Universe
- universe가 비어있으면 빈 결과 반환 (에러 아님)

### BR-5.3: Market Holiday
- 시장이 열리지 않은 날(주말/휴일)에는 scan 실행하지 않음
- MarketClock.is_market_open(today) == False → skip

---

## BR-6: Operator 가시성 규칙

### BR-6.1: Steering Channel Read-View
- `steering/watch_surge/` 디렉토리는 F4 steering read-view 범위 내
- Operator는 `steer_read` MCP tool로 파일 내용 조회 가능

### BR-6.2: 데이터 보존
- JSONL 파일은 삭제하지 않고 무기한 보존
- 디스크 사용량이 문제되면 별도 아카이빙 정책 적용 (현재는 PoC 단계이므로 보존)

---

## BR-7: EOD Flow Integration

### BR-7.1: 실행 순서
1. Market close event 발생
2. `SurgeDetector.scan()` 실행 → `steering/watch_surge/{date}.jsonl` 기록
3. EOD review turn 시작 (surge 데이터 포함)
4. Agent가 surge 분석 수행
5. `SurgeAnalysis` → `steering/watch_surge/{date}-analysis.jsonl` 기록

### BR-7.2: Surge Scan 실패 시
- scan 자체가 예외로 실패해도 EOD review turn은 정상 진행
- Agent는 surge-list 결과가 비어있는 것을 확인하고 surge 분석 생략

### BR-7.3: 급등주 없는 경우
- SurgeRecord가 0건이면 agent surge 분석 섹션은 "No surge stocks today"로 표시
- LLM 호출 불필요하게 surge 분석 지시 생략 (토큰 절약)

---

## Extension Rule Compliance

| Rule | Status | Rationale |
|------|--------|-----------|
| **Security Baseline** | N/A (Disabled) | Q7-1=B — PoC/실험적 기능 |
| **PBT-02** (pure function properties) | Applicable | `SurgeDetector._calculate_change_pct()`, `SurgeStore._is_duplicate()` 등 순수 함수에 Hypothesis 적용 |
| **PBT-03** (invariant preservation) | Applicable | `SurgeRecord` round-trip (model_dump_json → model_validate_json) |
| **PBT-07** (serialization) | Applicable | JSONL 라인 serialization/deserialization |
| **PBT-08** (idempotency) | Applicable | `write_records()` 중복 호출 시 결과 동일 |
| **PBT-09** (Hypothesis framework) | Applicable | `hypothesis` 라이브러리 사용 (기존 dev dependency) |

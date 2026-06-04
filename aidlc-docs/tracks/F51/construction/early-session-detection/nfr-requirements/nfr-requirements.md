# F51 Early-Session Detection — NFR Requirements

> **Unit**: `early-session-detection` | **Depth**: Minimal | **Reference**: F47 `surge-detection/nfr-requirements/`

## 1. Scalability

### NFR-SC-1: 심볼 수 확장
- 현재 유니버스 약 130종목 기준으로 설계. 500종목까지 선형 확장 가능해야 함.
- 다중심볼 `get_bars` 단일 API 호출로 처리하므로, API 호출 횟수는 O(1).
- 버퍼 메모리는 심볼당 (retention_minutes × bar_per_minute)개 BarRecord: 1종목당 최대 20개 레코드 × ~200바이트 = 4KB. 500종목 → 2MB. 충분히 감당 가능.

### NFR-SC-2: 일간 데이터량
- 이벤트당 덤프 파일: ~60 bars × ~150바이트 ≈ 9KB.
- 하루 예상 이벤트: 0~10건 (±5%/10분 엄격 기준). 최대 ~90KB/일.
- 연간: ~33MB. 보존 정책 불필요.

---

## 2. Performance

### NFR-PF-1: 폴링 응답 시간
- 다중심볼 `get_bars(130 symbols, limit=2)` 단일 API 호출은 5초 이내 완료.
- Alpaca IEX feed 기준 1분 봉이므로 데이터 양이 매우 작음.

### NFR-PF-2: Detection latency
- detection은 인메모리 버퍼에서 순수 함수로 동작 → O(symbols × window_bars) = 130 × 10 = 1,300회 연산. 밀리초 단위.
- 전체 tick() 한 사이클: fetch(~5s) + buffer(~ms) + detect(~ms) + dump(~ms) ≈ 5초 이내.

### NFR-PF-3: 폴링 간격
- `poll_interval_seconds` = 30초. fetch가 5초면 한 사이클에 25초 여유. 안정적.

---

## 3. Availability

### NFR-AV-1: Graceful degradation
- `early_session.enabled: false` → 모니터링 완전 스킵. 데몬 정상 동작.
- 마켓 홀리데이 → `market_clock.is_open()` 체크 후 스킵.

### NFR-AV-2: 부분 실패 격리
- 개별 종목 bar 조회 실패 → 해당 종목만 스킵 (BR-8.1).
- 전체 배치 실패 → tick 스킵, 다음 tick 정상 복구 (BR-8.2).

---

## 4. Security

### NFR-SE-1: 별도 보안 요구사항 없음
- Security Baseline OFF (Q7-1=B). PoC/실험적 기능.
- 데몬 내부 실행, 외부 네트워크 노출 없음.
- workspace/ 파일은 기존 steering 채널 보안 경계 내 (Token 기반).

---

## 5. Reliability

### NFR-RE-1: 데몬 재시작 복원
- 재시작 시 `_detected_today`는 `_index.jsonl`에서 복원 (BR-5.3).
- 버퍼는 휘발성 (인메모리) — 재시작 시 소실되나, 이미 덤프된 이벤트는 디스크에 보존.

### NFR-RE-2: Atomic writes
- 인덱스 append: `os.replace()` 원자적 쓰기 (BR-7.2).
- 덤프 파일: `write_before`는 신규 파일 생성, `write_after`는 append. 마지막 라인 손상에 대비해 JSONL 라인 단위 복구 가능 (BR-6.6).

---

## 6. Maintainability

### NFR-MA-1: Zero new runtime dependencies
- stdlib `collections.deque`, `json`, `pathlib`, `datetime` + 기존 `pydantic`, `APScheduler`, `loguru` + `alpaca-py` (이미 설치됨).
- F47과 동일: `pip check` 통과, `pyproject.toml` 변경 없음.

### NFR-MA-2: Config-driven
- 모든 감지/덤프 파라미터는 `settings.yaml` → `early_session:` 블록에서 조정 가능 (BR-9).
- 코드 변경 없이 임계값, 시간窗口, 폴링 간격 튜닝 가능.

### NFR-MA-3: 모듈 격리
- `src/early_session/` 독립 패키지. 기존 모듈과의 결합은 provider(`get_bars`)와 config(`settings.yaml`)뿐.
- 다른 시스템(intraday, surge, trading)에 영향 없음.

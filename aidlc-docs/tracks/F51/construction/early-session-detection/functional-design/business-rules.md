# F51 Early-Session Detection — Business Rules

> **Unit**: `early-session-detection` | **Reference**: `requirements.md` FR-1~FR-6, NFR-1~NFR-4

---

## BR-1: 모니터링 시간 범위

| Rule | Detail |
|------|--------|
| **BR-1.1** | 모니터링은 정규장 오픈 09:30 ET에 시작하여 10:30 ET에 종료한다 (Q1=D). |
| **BR-1.2** | 마켓 홀리데이, 조기 마감(half-day)에는 모니터링을 실행하지 않는다. 마켓 캘린더(`market_clock.is_open()`)로 판단. |
| **BR-1.3** | 데몬이 09:30~10:30 사이에 재시작된 경우, 남은 시간 동안만 모니터링을 수행한다. 이미 지나간 시간의 데이터는 수집하지 않는다. |

---

## BR-2: 데이터 폴링

| Rule | Detail |
|------|--------|
| **BR-2.1** | `poll_interval_seconds`(기본 30초) 간격으로 유니버스 전체 종목의 1분 봉을 폴링한다. |
| **BR-2.2** | AlpacaDataProvider의 다중심볼 `get_bars(symbols, timeframe=MINUTE_1, limit=2)`로 단일 API 호출한다. |
| **BR-2.3** | 각 폴링은 최근 2개 봉을 요청한다 (`limit=2`). 30초 간격이므로 보통 1개 신규 봉이 도착한다. 이전 tick에서 누락된 봉도 수집 가능하도록 2개. |
| **BR-2.4** | 폴링 실패(네트워크 오류, API 오류) 시 해당 tick은 스킵하고 로그를 남긴다. 다음 tick에서 정상 복구된다. |

---

## BR-3: 순환 버퍼

| Rule | Detail |
|------|--------|
| **BR-3.1** | 각 종목의 BarRecord는 `buffer_retention_minutes`(기본 20분 = dump_before 15분 + 여유 5분) 동안만 유지한다. |
| **BR-3.2** | 매 `push()` 호출 시 cutoff(`now - retention_minutes`)보다 오래된 레코드는 FIFO로 제거한다. |
| **BR-3.3** | 종목별 deque는 독립적이다. 한 종목의 버퍼 오버플로우가 다른 종목에 영향을 주지 않는다. |
| **BR-3.4** | 신규 종목이 유니버스에 추가된 경우, 첫 push 시 자동으로 deque가 생성된다. |

---

## BR-4: 시그널 감지

| Rule | Detail |
|------|--------|
| **BR-4.1** | `window_minutes`(기본 10분) 동안의 `close` 가격 변화율이 `threshold_pct`(기본 ±5%) 이상일 때 시그널로 감지한다 (Q1=D). |
| **BR-4.2** | `bars[0].close`(window 시작)와 `bars[-1].close`(window 끝=현재)를 기준으로 계산한다: `change_pct = (last - first) / first * 100`. |
| **BR-4.3** | `change_pct >= +threshold_pct` → `direction = "surge"` |
| **BR-4.4** | `change_pct <= -threshold_pct` → `direction = "drop"` |
| **BR-4.5** | `abs(change_pct) < threshold_pct` → 감지 안 함 (`None` 반환). |
| **BR-4.6** | `len(bars) < window_minutes`(데이터 부족) → 감지 안 함. 장초반 초기 몇 분 동안은 버퍼가 덜 쌓였으므로 자연스럽게 감지되지 않는다. |

---

## BR-5: Idempotency (중복 감지 방지)

| Rule | Detail |
|------|--------|
| **BR-5.1** | 동일 종목은 하루에 **최초 1회만** 감지한다 (Q3=A). |
| **BR-5.2** | 감지된 심볼은 `_detected_today: set[str]`에 추가되고, 이후 tick에서 스킵된다. |
| **BR-5.3** | 데몬 재시작 시 `workspace/early_session/{today}/_index.jsonl`에서 이미 감지된 심볼을 읽어 `_detected_today`를 복원한다. |
| **BR-5.4** | `_index.jsonl`이 없는 경우(당일 첫 실행) → 빈 set에서 시작. |

---

## BR-6: 구간 덤프

| Rule | Detail |
|------|--------|
| **BR-6.1** | 감지 즉시 `before` 구간(`detected_at - dump_before_minutes` ~ `detected_at`)의 bar들을 덤프한다 (Q2=C: 15분 전). |
| **BR-6.2** | `after` 구간은 `detected_at`부터 `detected_at + dump_after_minutes`(Q2=C: 45분 후)까지 추가 수집하여 append한다. |
| **BR-6.3** | 덤프 파일명: `{symbol}_{HHMMSS}_{direction}.jsonl` (예: `AAPL_094532_drop.jsonl`). |
| **BR-6.4** | 파일은 `workspace/early_session/{YYYY-MM-DD}/` 아래 생성된다. |
| **BR-6.5** | `before` 덤프 시점에 버퍼에 충분한 데이터가 없는 경우(clamp된 start), 가용한 데이터만 덤프한다. |
| **BR-6.6** | `after` 덤프 구간이 10:30 ET를 초과하는 경우, 10:30에 도달하면 즉시 finalize하여 가용한 after 데이터만 기록한다. |

---

## BR-7: 인덱스 기록

| Rule | Detail |
|------|--------|
| **BR-7.1** | 덤프 완료(finalize) 시에만 `_index.jsonl`에 레코드를 append한다. |
| **BR-7.2** | `_index.jsonl` append는 atomic write(`os.replace()`)로 수행한다. |
| **BR-7.3** | 인덱스의 `data_file`는 `workspace/early_session/` 기준 상대 경로로 기록한다. |

---

## BR-8: 에러 처리 (Fail-Closed)

| Rule | Detail |
|------|--------|
| **BR-8.1** | 개별 종목의 bar 데이터 조회 실패 → 해당 종목만 스킵, 다른 종목은 정상 처리. |
| **BR-8.2** | 전체 배치 `get_bars` 실패 → 해당 tick 전체 스킵, 로그 기록. 다음 tick에서 재시도. |
| **BR-8.3** | 덤프 파일 쓰기 실패 → 로그 기록 후 이벤트 드롭 (idempotency set에는 추가 — 무한 재시도 방지). |
| **BR-8.4** | 인덱스 쓰기 실패 → 로그 기록. 덤프 파일은 존재하지만 인덱스에 없는 상태 허용 (수동 복구 가능). |
| **BR-8.5** | `detector.detect()`는 순수 함수이므로 절대 예외를 발생시키지 않는다. 입력 검증은 호출부에서 수행. |

---

## BR-9: 설정 우선순위

| Rule | Detail |
|------|--------|
| **BR-9.1** | `config/settings.yaml` → `early_session:` 블록 > 코드 내 기본값. |
| **BR-9.2** | `early_session.enabled: false` → 모니터링 전체 비활성화 (데몬 job이 스킵). |
| **BR-9.3** | `early_session.symbols`가 명시되지 않은 경우 `trading.symbols`를 기본값으로 사용. |

---

## BR-10: Operator 가시성

| Rule | Detail |
|------|--------|
| **BR-10.1** | `workspace/early_session/` 디렉토리는 steering 채널의 read-view 범위 내에 위치한다 (F4 contract). |
| **BR-10.2** | CLI 도구(`python -m early_session inspect --date 2026-06-03`)로 당일 이벤트 목록과 시계열 데이터 조회가 가능해야 한다. |

---

## BR-11: 저장소 정리

| Rule | Detail |
|------|--------|
| **BR-11.1** | `workspace/early_session/{date}/` 디렉토리에는 해당 날짜의 이벤트 시계열 파일들과 `_index.jsonl`이 저장된다. |
| **BR-11.2** | 별도 보존 정책은 없음 — 수동 정리 또는 추후 트랙에서 자동화. 현재는 무기한 보존. |

---

## Business Rules → Requirements Traceability

| BR | Requirements |
|----|-------------|
| BR-1 | FR-1.1 |
| BR-2 | FR-1.1, FR-1.4 |
| BR-3 | FR-1.2, FR-1.3 |
| BR-4 | FR-2.1, FR-2.2 |
| BR-5 | FR-2.4 |
| BR-6 | FR-3.1, FR-3.2, FR-3.3, FR-3.4 |
| BR-7 | FR-4.1, FR-4.2, FR-4.3 |
| BR-8 | NFR-2.1, NFR-2.2, NFR-2.4 |
| BR-9 | NFR-3.1 |
| BR-10 | FR-5.1, FR-5.2 |
| BR-11 | NFR-1.2 |

---

## PBT 대상 식별

PBT Partial 적용 (Q7-2=B — 순수 함수 + serialization round-trip):

| 대상 | 종류 | PBT 적용 |
|------|------|----------|
| `SignalDetector.detect(bars) → SignalEvent \| None` | 순수 함수 | ✅ Hypothesis |
| `BarRecord ↔ dict ↔ JSONL line` | Serialization round-trip | ✅ Hypothesis |
| `EventIndex ↔ dict ↔ JSONL line` | Serialization round-trip | ✅ Hypothesis |
| `DumpWindow.start/end clamp` | 순수 함수 | ✅ Hypothesis |
| `BufferManager.push/pop` | Stateful (비대상) | 일반 단위 테스트 |
| `WindowDumper.write_before/after` | I/O (비대상) | 일반 단위 테스트 |
| `EarlySessionMonitor.tick()` | Orchestrator (비대상) | 통합 테스트 |

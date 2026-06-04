# F56 Requirements — code-review 후속 버그 수정 + early-session 모니터 연결

**Depth**: Standard (버그 정의는 명확하나 모니터 스케줄러 연결이 통합 작업 포함)
**Type**: Bugfix + Integration
**Source**: `/code-review` (범위 `c76d682..faec7b7`, 머지된 F51/F53/F52/F47/F50)

## 배경
직전 코드리뷰에서 6개 결함을 검출. 사용자 결정으로 **6개 전부 수정 + 현재 미연결 상태인
`EarlySessionMonitor`를 스케줄러에 실제 연결**까지 본 트랙 범위에 포함.

## Functional Requirements

### FR-1 (BUG-1, High) — surge 감지가 prev_close를 얻을 수 있어야 한다
- **현재**: `BaseDataProvider.get_daily_bar()`가 `[당일 00:00, 익일 00:00)` 1일 구간만 조회 →
  일봉 1개만 반환 → `prev_close=None` → `SurgeDetector._scan_one()`이 모든 종목을 임계 미달 처리 →
  EOD surge 스캔이 **항상 0건**.
- **요구**: `get_daily_bar(symbol, d)`는 `d` 당일 OHLCV와 **직전 거래일 종가(prev_close)**를 함께
  반환해야 한다. 주말/공휴일을 고려해 조회 시작을 충분히 앞으로 둔다(예: `d - 7일`).
- **수용 기준**: 다거래일 일봉을 반환하는 페이크 provider로 `get_daily_bar`가 `prev_close`를
  올바르게 채우고, `SurgeDetector.scan()`이 임계 초과 종목 레코드를 생성한다.

### FR-2 (BUG-2, High) — early-session 모니터 종료시각이 ET 기준이어야 한다
- **현재**: `start()`가 `datetime.now(UTC)`에 `monitor_end_et`("10:30" ET)를 그대로 `replace` →
  종료시각이 UTC로 해석 → 장중 첫 tick에 `now >= monitor_end`가 즉시 참 → 모니터 즉시 종료.
- **요구**: 모니터의 시각 비교는 **ET(`ZoneInfo("America/New_York")`) 기준**으로 일관되게 한다
  (코드베이스 기존 패턴과 동일). `monitor_end`는 ET 당일 `monitor_end_et` 시각의 tz-aware datetime.
  `today`/일중 기준 시각도 ET로 통일.
- **수용 기준**: 09:30 ET에 `start()` 호출 후 첫 `tick()`에서 즉시 stop되지 않고, ET `monitor_end`
  도달 시(그리고 pending finalize 없음) stop된다.

### FR-3 (BUG-3, Med-High) — executor cursor가 dedup으로 밀려난 결정에 막히지 않아야 한다
- **현재**: `execute_pending()`이 latest-by-symbol dedup으로 건너뛴 인덱스를 `terminal_indices`에
  넣지 않아, cursor 전진 루프가 그 인덱스에서 영구 정체. 세션 동안 `pending` 재스캔과
  `terminal_indices`(정렬·영속)가 무한 증가.
- **요구**: 같은 심볼의 더 나중 결정에 의해 **슈퍼시드된(처리 대상에서 제외된) 인덱스**는
  terminal로 간주해 cursor가 통과할 수 있어야 한다. 재시도 대상(`no_order`/`error`)인 "최신" 결정은
  여전히 cursor를 멈춰 다음 사이클에 재처리(기존 의도 유지). 이미 terminal인 인덱스는 재실행 금지(유지).
- **수용 기준**: (a) 슈퍼시드 중복이 앞에 있어도 cursor가 전진, (b) 최신 결정이 `error`/`no_order`면
  cursor가 그 앞에서 정지하고 재처리, (c) terminal 결정은 재실행되지 않음 — 단위 테스트로 검증.

### FR-4 (BUG-4 + BUG-6, Med/Low) — finalize가 None 이벤트로 크래시하지 않아야 한다
- **현재**: finalize 시 원본 `SignalEvent`를 잃어버리고 동일 윈도우로 재감지 → None이면
  `write_after(None,…)`/`index_writer.append(None,…)`에서 `AttributeError`. 매 tick 반복 크래시.
  `first_bar` 미사용 등 죽은 복구 코드 존재(BUG-6).
- **요구**: 감지 시점의 `SignalEvent`를 보관했다가 finalize에서 **그대로 사용**(재감지·재구성 금지).
  죽은 복구 분기 제거. `_pending_finalizes`를 `symbol → (event, finalize_at)`로 변경.
- **수용 기준**: 감지 후 재트리거가 사라져도 finalize가 보관된 event로 정상 덤프/인덱싱하며 예외 없음.

### FR-5 (BUG-5, Med) — 버퍼 보존시간이 덤프 윈도우를 모두 덮어야 한다
- **현재**: `buffer_retention_minutes(20)` < `dump_after_minutes(45)` → finalize 시 after-window
  앞부분 유실, `bar_count` 과소 계산.
- **요구**: 유효 버퍼 보존시간 ≥ `dump_before_minutes + dump_after_minutes (+ window/margin)`이
  되도록 보장(설정 검증 또는 모니터에서 도출). 설정 기본값도 정합화.
- **수용 기준**: 감지~finalize 동안 before/after 전체 구간 바가 버퍼에 남아 덤프된다.

### FR-6 (Integration) — EarlySessionMonitor를 스케줄러에 연결
- **요구**: `AgentTradingMode.start()`에서 `config.early_session.enabled`일 때
  `EarlySessionMonitor`를 생성하고 스케줄러에 등록한다.
  - `add_market_open_job(monitor.start, "early_session_start")` — 09:30 ET 시작.
  - `add_seconds_job(monitor.tick, poll_interval_seconds, "early_session_tick")` — tick은
    `not _running`이면 즉시 반환(no-op)하므로 상시 등록 안전.
  - `monitor.stop()`은 `monitor_end` 도달 시 자체 종료.
  - 데이터 provider = `executor.data_provider`, workspace_root = `executor.journal.root`,
    universe = `executor.universe`(주입).
- **수용 기준**: 데몬 기동 시 early_session 잡이 등록되고, 비활성(`enabled: false`) 시 미등록.
  tick이 모니터링 윈도우 밖에서 no-op.

## Non-Functional Requirements
- **NFR-1 동작 보존**: FR-1~5는 버그 수정 — 정상 경로 동작/시그니처 변경 금지(`get_daily_bar`,
  `execute_pending` 반환형 유지). FR-6만 신규 통합.
- **NFR-2 견고성**: 스케줄러 잡은 예외로 데몬을 죽이면 안 됨(기존 NFR-4 패턴: tick/start는
  best-effort, 예외 로깅 후 계속).
- **NFR-3 (PBT, Partial)**: 순수 함수(`SignalDetector.detect`, `SurgeDetector._calculate_change`)와
  JSONL 직렬화 라운드트립(`bar_to_jsonl`↔`bar_from_jsonl`, `event_index_to/from_jsonl`)에 한해
  Hypothesis 속성 테스트 작성.

## Out of Scope
- early_session 이벤트의 에이전트 분석 프롬프트/턴 연동(별도 기능).
- surge/early_session 외 다른 리뷰 외 영역.

## Extension Configuration
- **Security Baseline**: Disabled (사용자 opt-out — 내부 버그 수정, 새 공격 표면 없음).
- **Property-Based Testing**: Enabled (Partial) — 위 NFR-3 범위.

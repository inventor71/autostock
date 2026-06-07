# F69 요구사항 — Health Check TUI 통합

> 깊이: **standard** · brownfield · F63(`src/monitoring/health`) 후속.
> 설계 방향은 사용자와 사전 확정(데몬 백그라운드 발행 + 상단바 글리프 + 상세 오버레이).

## 1. 배경 / 문제
F63에서 9차원 read-only health check 모듈(`src/monitoring/health/run_all_checks`)과 독립 실행
스크립트(`scripts/health.py`)를 만들었으나, 운영자가 별도로 스크립트를 돌려야만 시스템 상태를
볼 수 있다. 운영자는 이미 TUI(`operator-console/cli/packages/tui-trading`)를 보고 있으므로,
health 상태를 TUI 안에서 상시 보이게 하면 "따로 돌리기"가 사라진다.

## 2. 의도 분석 (intent)
- **무엇을**: health 리포트를 데몬이 주기 발행하고 TUI가 표시.
- **왜**: 별도 실행 없이 한 화면에서 시스템 건강 상태 인지 → 이상 조기 발견.
- **명확도**: 높음 (아키텍처/표시 방식 사전 확정).

## 3. 기능 요구사항 (FR)

### Producer (Python 데몬)
- **FR-1**: 에이전트 데몬은 steering이 활성일 때, 스케줄러 풀의 **별도 워커**에서 주기적으로
  health를 점검해 발행한다. **주기 발행은 외부 호출 없는 cheap 차원 subset**
  (process/logs/config_env/resources) + 데몬이 이미 가진 `last_snapshot` 파생(account/market)만
  사용한다 (critic HIGH 대응: 전체 9차원은 broker 5개 생성 + 매회 실제 LLM API ping을 유발).
  기본 주기 설정 가능. 2초 command-poll·5초 snapshot·trade 버스를 절대 막지 않는다.
  **전체 9차원 deep check는 `scripts/health.py` 수동 실행에 한정**(FR-4).
- **FR-2**: 결과 `HealthReport`를 `steering/health.json`에 **원자적**으로 쓴다
  (`atomic_write_text` 사용 — monitor.json과 동일 패턴). 페이로드는 `report.model_dump(mode="json")`
  (run_id, ts, duration_ms, overall, summary, dimensions{9}).
- **FR-3**: health 체크 자체가 예외를 던져도 데몬은 죽지 않는다. 실패 시 직전 health.json을
  유지하거나(선호) overall=CRITICAL + 사유를 담은 최소 리포트를 쓴다 (graceful degradation).
- **FR-4**: 기존 `scripts/health.py` 독립 실행 경로는 그대로 유지(공존, 회귀 없음).

### Consumer (TUI — TS/opentui/SolidJS)
- **FR-5**: `use-monitor-data.ts` 패턴을 미러한 `use-health-data.ts` 훅이 `steering/health.json`을
  주기 폴링(poll-and-diff: 의미 있는 필드 변할 때만 시그널 갱신, ts 등 휘발 필드 제외).
  파일 부재/torn read 시 직전 양호값 유지(상태바를 통째로 "disconnected"로 뒤집지 않음).
- **FR-6**: 상단 상태바에 health **글리프 + 색상** 표시 (✓ OK=green, ⚠ WARNING=yellow,
  ✗ ERROR=red, ⊘ CRITICAL=red/강조, ○ SKIPPED/stale=dim). health.json 자체가 없거나
  오래된(stale) 경우의 표시도 정의(예: dim ○ "no data").
- **FR-7**: 지정 키 입력 시 9차원 상세 **오버레이**를 연다(`turn-overlay.tsx` 패턴 — z-order/
  hit-test 규약 준수 [[opentui-zorder-hittest]]). 각 차원의 status + 실패/경고한 sub-check
  detail을 보여준다. 다시 키/ESC로 닫는다.

## 4. 비기능 요구사항 (NFR)
- **NFR-1 (성능/격리)**: 발행 주기 기본 **5분**(설정값으로 5~10분 조정 가능). health 체크가
  스케줄러/버스/핫루프와 **독립 스레드**에서 돌아 트레이딩 경로 지연 0.
- **NFR-2 (안전/read-only/외부호출 없음)**: health 모듈은 read-only(F63 보장). **주기 발행은
  외부 호출 0** — cheap 차원(로컬 파일·proc·disk)만 + 스냅샷 재사용. broker/LLM/network
  미접촉. 발행은 파일 쓰기만. 비차단. (전체 9차원의 외부 호출은 scripts/health.py에 한정.)
- **NFR-3 (TUI 무churn)**: 폴링 diff로 불필요한 리렌더/깜박임 방지 (monitor 훅 선례).
- **NFR-4 (회귀 없음)**: steering off거나 health.json 없을 때 TUI는 정상 동작(글리프만 dim).

## 5. 범위 밖 (out of scope)
- health 점검 로직 변경(차원 추가/수정)은 본 트랙 범위 아님 (F63/F66 소관).
- CronCreate/외부 스케줄러 기반 알림 — 본 트랙은 TUI 표시에 집중(Slack/Telegram 알림은
  F63 AlertManager 경로 그대로, 변경 없음).
- 과거 health 이력 타임라인/저장 — 본 트랙은 최신 1건 표시.

## 6. 가정
- 데몬과 TUI는 동일 `steering/` 디렉터리를 공유(기존 monitor.json/snapshot.json과 동일 경로).
- 단일 운영자 페르소나 → User Stories skip 정당.

## 7. 확정된 결정 (2026-06-06, AskUserQuestion)
- **D1 (Extension opt-in)**: Security Baseline = **Disabled**, Property-Based Testing = **Disabled**
  (F63과 동일 — read-only 운영도구, 결정적 출력, 새 보안 민감 면 없음).
- **D2 (발행 주기 기본값)**: **5분** (설정값으로 조정 가능). → FR-1/NFR-1 확정.
- **D3 (오버레이 트리거)**: **상단바 health 글리프 클릭**으로 토글 (기존 turn/symbol/intervention
  오버레이의 클릭-anchor 패턴 일관, 새 전역 키 불필요). → FR-7 확정. ESC/재클릭으로 닫기.

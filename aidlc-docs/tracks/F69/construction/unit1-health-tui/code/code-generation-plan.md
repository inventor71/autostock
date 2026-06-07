# F69 Unit 1 — Code Generation Plan & Result

설계(functional-design.md) + critic 반영안을 구현. 전부 worktree `feat/F69`에서 작성.

## Producer (Python)
- [x] `config/config.py` — `MonitoringConfig.health_publish_seconds: int = 300` (0=off)
- [x] `src/agent/steering/runtime.py`
  - [x] imports: `CheckerDispatcher` + cheap checkers(Process/Log/ConfigEnv/Resource) + report types + `get_settings`
  - [x] `publish_health()` — cheap subset 실행 → `_augment_health_from_snapshot` → `health.json` 원자적 쓰기 + `publish_interval_seconds` 동봉. best-effort(예외 삼킴).
  - [x] `_augment_health_from_snapshot()` — `self.last_snapshot`에서 account/market 파생(broker 호출 0), overall/summary는 `CheckerDispatcher._overall/_build_summary` 재사용
- [x] `src/trading/modes/agent.py` — steering 블록에 `add_seconds_job(publish_health, health_publish_seconds, "steering_health")` (0이면 미등록)

## Consumer (TUI / TS)
- [x] `types.ts` — `HealthStatus/HealthCheck/HealthDimension/HealthReport` + `OverlayState`에 `"health"` + `health` 필드
- [x] `utils/format.ts` — `healthGlyph()/healthColor()` (OK✓/WARN⚠/ERR✗/CRIT⊘/SKIP○ + stale dim)
- [x] `hooks/use-health-data.ts` (신규) — `health.json` poll-diff(verdict 시그니처만), stale은 비반응 ts/interval 추적(무churn), torn-read 가드
- [x] `hooks/use-overlay.ts` — `openHealth()` 토글 + 기존 open*에 `health:null`
- [x] `components/health-overlay.tsx` (신규) — OverlayPanel 기반 9차원 평면 리스트(non-OK check만 펼침)
- [x] `components/timeline-bar.tsx` — NavRow 우측에 `· ⟨glyph⟩ hp` 클릭 셀 + props(health/healthStale/onHealthClick)
- [x] `index.ts` — `useHealthData/HealthOverlay` export
- [x] opencode `routes/session/index.tsx` — `useHealthData` 배선 + TimelineBar props + HealthOverlay 컨테이너

## 테스트
- [x] `tests/test_f69_health_publish.py` (6 케이스): 파일 shape / **expensive 차원 미포함(critic HIGH 회귀가드)** / account SKIPPED(no snapshot) / account 파생 / 음수 cash WARNING / 예외 비전파

## 검증 결과
- Python: `test_f69_health_publish` 6/6 + `test_steering_runtime` 9/9 통과, agent.py 파싱 OK
- 라이브 스모크: cheap dispatcher 30ms, **AlpacaBroker init 로그 0건**(broker 미생성 확인)
- TS: monorepo `bun run typecheck` 19/19 통과. 신규 .tsx/types 에러 0 (standalone fs/path 노이즈는 기존 훅 공통)

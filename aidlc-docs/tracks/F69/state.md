# Track F69 — Health Check TUI 통합

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F69
- **Title**: Health Check TUI 통합 — 데몬 발행 + TUI 글리프/오버레이 (F63 후속)
- **Type**: feature
- **Status**: merge-awaiting  <!-- active → merge-awaiting (set when Build & Test passes) → merged (by /ai-dlc-merge) -->
- **Branch**: feat/F69
- **Worktree**: .claude/worktrees/F69
- **Submodule branch**: — (monorepo; operator-console/cli/packages/tui-trading 변경 포함)
- **Base commit**: ec2875c
- **Start Date**: 2026-06-06

## Extension Configuration
- **Security Baseline**: Disabled — N/A (read-only 운영도구; steering/health.json은 파일 쓰기만,
  새 보안 민감 면 없음. F63과 동일)
- **Property-Based Testing**: Disabled — N/A (단순 발행/폴링·diff, 결정적 출력)

## Scope
F63에서 만든 `src/monitoring/health` (9차원 read-only health check)를 운영 중인 TUI에 통합.
별도 스크립트(`scripts/health.py`)를 따로 돌리지 않고 TUI에서 시스템 건강 상태를 본다.

- **Producer (Python)**: steering 데몬이 별도 백그라운드 스레드에서 주기적(5~10분)으로
  `run_all_checks()`를 호출 → `steering/health.json`에 `HealthReport` 발행.
  데몬 1.5초 핫루프에는 넣지 않음 (외부 API ~3초). 읽기 전용·비차단·graceful degradation.
- **Consumer (TUI, `operator-console/cli/packages/tui-trading`, TS/opentui/SolidJS)**:
  `use-monitor-data.ts` 패턴을 미러한 `use-health-data.ts` 훅으로 `steering/health.json`
  poll-and-diff. 상단 상태바에 health 글리프(✓/⚠/✗/⊘ 색상) + 키 입력 시
  `turn-overlay.tsx` 패턴 오버레이로 9차원 상세 표시.
- 기존 `scripts/health.py` 독립 실행 경로는 유지(공존).

F63 health 모듈 후속.

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성.

- **공유 파일 (주의)**: `src/agent/steering/runtime.py`(메서드 2개 추가, 기존 미변경),
  `src/trading/modes/agent.py`(steering 블록에 1 job 추가), `config/config.py`(MonitoringConfig 필드 1),
  TUI `timeline-bar.tsx`/`use-overlay.ts`/`types.ts`/`index.ts`/`format.ts`(전부 additive),
  opencode `routes/session/index.tsx`(import+배선).
- **API/시그니처 변경**: 없음 (전부 additive — 신규 메서드/필드/파일/optional props).
- **알려진 동시 변경**: 없음. (F33 paused; M1 rules/docs와 무관.)

## Stage Progress
- [x] Workspace Detection
- [x] Requirements Analysis — standard (승인 대기)
- [ ] User Stories — skip (운영 도구, 단일 운영자 페르소나)
- [x] Workflow Planning (승인 대기)
- [ ] Application Design — skip (단순, Functional Design에 흡수)
- [ ] Units Generation — skip (단일 유닛, Python producer + TS consumer)
- [x] Construction (per-unit Code Generation)
  - [x] Unit 1 — Daemon health publisher + TUI health hook/glyph/overlay
    - [x] Functional Design (minimal) — 승인 + critic 반영
    - [x] NFR Req/Design — skip (requirements NFR-1~4)
    - [x] Infra Design — skip
    - [x] Code Generation — Python(runtime/config/agent) + TS(types/format/hook/overlay/timeline/host) + tests
- [x] Build & Test — pytest 187 passed, tsgo 19/19, 라이브 스모크 OK, post-merge-guide 작성 → merge-awaiting

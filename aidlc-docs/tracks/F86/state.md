# Track F86 — 모바일 대시보드 데이터 엔드포인트 (F79 후속, 실데이터 배선)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F86
- **Title**: 모바일 대시보드 데이터 엔드포인트 — PWA `/autostock` 대시보드에 실데이터 공급 (F79 후속)
- **Type**: feature
- **Status**: merge-awaiting  <!-- re-enqueued after code-review fixes, re-verified green 2026-06-16 -->
- **Branch**: feat/F86
- **Worktree**: .claude/worktrees/F86
- **Submodule branch**: — (monorepo; operator-console/cli 변경 예상)
- **Base commit**: f7b751d (main HEAD at branch creation)
- **Start Date**: 2026-06-14T07:00:47Z

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | Yes | Requirements Analysis |
| Property-Based Testing | Yes (full) | Requirements Analysis |

### Locked decisions (Requirements Analysis, 2026-06-14)
- **Transport**: 폴링 GET (`GET /autostock/dashboard`, 클라 ~5s 폴), F79 staleness 코어 재사용.
- **Read auth**: basic-auth + tailscale TLS만 (read=비-mutating → 패스키 서명 면제, webauthn.ts READONLY 정책과 동일선상).
- **v1 scope**: account / positions(P&L) / health / pending / market session / agent recent activity. **portfolio history는 제외 → F84로.**

## Scope
F79가 남긴 명시적 후속: 모바일 PWA `/autostock` 셸의 DashboardView가 현재 EMPTY_MODEL을
렌더(빈-모델 + "데이터 연결 후속" 고지). 이 트랙은 **opencode serve 서버에 autostock read
엔드포인트**를 추가해, 데몬이 발행하는 steering 산출물(`snapshot.json`/`health.json`/
`pending_approvals.json` 등)을 모바일 대시보드 모델로 공급한다.

- 서버: `operator-console/cli/packages/opencode/src/server/autostock/` 에 read 라우트 추가
  (webauthn.ts 와 동형 fork-isolated 마운트).
- 클라: `mobile-shell.tsx`가 read 엔드포인트를 폴링/구독 → 기존 `assembleSnapshot`/`toDashboard`
  (F79 C2/U3) 코어로 모델 조립 → DashboardView 실데이터 렌더 + staleness(NFR-7).
- 데이터 소스: 데몬 steering_dir의 발행 JSON (브로커 직접 호출 아님 — read 경로는 파일 기반).
- F84(모바일 차트)가 이 데이터(특히 portfolio history)에 의존 — 인접 스택.

관련: [[worktree-live-verification]], F79/F71/F75 보안 백본.

## Merge Risk Notes
- **공유 파일 (주의)**:
  - `operator-console/cli/packages/opencode/src/server/server.ts` — fetch 체인에 1줄 추가(webauthn 다음). 충돌 가능성 낮음.
  - `operator-console/cli/packages/opencode/package.json` + `bun.lock` — `fast-check@4.6.0` devDep 추가. 다른 트랙이 lock 건드리면 `bun install` 재실행.
  - `mobile-shell.tsx` — F84(모바일 차트)가 같은 셸을 건드릴 수 있음. F84는 이 데이터 채널 위에 스택 예정이라 본 트랙 선행 권장.
- **신규 파일(충돌 무관)**: `server/autostock/dashboard-read.ts`, `addons/autostock/dashboard-source.ts` (+각 테스트).
- **API/시그니처 변경**: 없음(추가형). 데몬(python) 발행 스키마는 read-only 의존, 무변경.
- **알려진 동시 변경**: F84(모바일 차트, 같은 데이터·셸 의존), F79 머지 완료.
- **Base**: 브랜치 시점 base는 state 상단 `f7b751d`로 기록됐으나 worktree는 `f17a36f`(advanced main)에서 분기됨 — rebase 시 f17a36f 기준.

## Stage Progress
- [x] Workspace Detection
- [x] Requirements Analysis — standard (approved 2026-06-14)
- [x] User Stories — SKIP (F79 스토리 재사용, 단일 후속 배선)
- [x] Workflow Planning (approved 2026-06-15)
- [x] Application Design — EXECUTE (approved 2026-06-16)
  - OQ-1 직접 파일 read / OQ-1b STEERING_DIR env / OQ-2 monitor.json market / OQ-3 monitor.json current_turn+decisions
  - 갭: day_pnl_pct·buying_power 미발행 → v1 null (사용자 승인)
- [x] Units Generation — SKIP (단일 유닛)
- [x] Construction
  - [x] Functional Design — EXECUTE (domain-entities/business-rules/business-logic-model/frontend-components + PBT-01 P1~P6)
  - [x] NFR Requirements/Design — SKIP (requirements.md NFR-1~6 + fast-check 확정; 보안/PBT 교차강제)
  - [x] Infrastructure Design — SKIP (인프라 무변경)
  - [x] Code Generation — Mobile dashboard data endpoint (feat/F86)
    - 서버: dashboard-read.ts(C1/C2/C3) + server.ts 마운트 + opencode test 13 pass
    - 클라: dashboard-source.ts + mobile-shell 폴링 배선 + app addon test 52 pass
    - real-data 스모크로 버그 2건(미정규화 카운트, health overall 스키마) 발견·수정
- [x] Build & Test — typecheck/unit/PBT/회귀/real-data 스모크 ALL GREEN → merge-awaiting
- [x] Code Review (/code-review high) — 5 findings, 수정 적용 후 재검증 그린:
  - **#1 [HIGH] published_at 앵커 오류**: monitor.ts(독립 타이머)로 신선도 판정 → 데몬 publish_snapshot 실패로 snapshot.json 동결돼도 fresh로 위장(NFR-2 위반). 수정: snapshot.json 자체 `published_at`(채널이 write 시에만 갱신) → mtime → null. real-data 스모크로 확인.
  - **#2 [MED] 클라 staleness 시계 동결**: http() 부재 시 poll 조기반환으로 nowMs 동결 → stale 미발화. 수정: interval이 매 tick nowMs 무조건 갱신 후 네트워크 poll만 스킵.
  - **#3 [MED] resolveSteeringDir cwd 폴백**: STEERING_DIR/AUTOSTOCK_ROOT 미설정 시 cwd 상대경로 추정 → 1회 console.warn 추가 + post-merge-guide 전제조건 명시.
  - **#5 [LOW] position_count 불일치**: account.position_count 신뢰 → positions.length 단일소스로 변경(F79 코어와 정합).
  - **#4 [LOW] recent[].ts 'HH:MM'**: ISO 아님 — 타입 주석으로 표시(Date.parse 금지). 데몬 ISO 발행은 후속.
  - auth-bypass 의혹은 refuted(fail-closed 확인).

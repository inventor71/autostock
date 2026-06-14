# Track F73 — viz-shell: 읽기 전용 생성형 대시보드 사이드카 (vibeOS 패턴 방향 A)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F73
- **Title**: viz-shell — 읽기 전용 생성형 대시보드 사이드카 (vibeOS 패턴 방향 A)
- **Type**: feature
- **Status**: active
- **Branch**: `vibeshell` (사용자 지정 — `feat/F73` 컨벤션 대신 명시 요청)
- **Worktree**: .claude/worktrees/F73 (2026-06-13 생성)
- **Submodule branch**: — (monorepo; operator-console/cli 미접촉 예정)
- **Base commit**: 5a00442 (최신 main에서 분기 — R13·F75 머지 포함; 트랙 생성 시점 main = 76ff7b6)
- **Start Date**: 2026-06-12T00:07:10Z

## Merge Policy (사용자 지정 — 표준과 다름, 글로벌 룰 명시적 override)
> **장기 브랜치.** 사용자 지시: "vibeshell이라는 다른 브랜치에서 진행하는 방식으로 나중에
> 충분히 안정되었을 때 머지". Build & Test green이어도 **자동으로 `merge-awaiting`으로
> 전환하지 않는다** — 사용자가 명시적으로 "안정됐다, 머지하자"고 선언할 때까지 `active` 유지.
> `/ai-dlc-merge` 큐에 조기 진입 금지.
>
> ⚠️ 이 정책은 CLAUDE.md Build-and-Test Step 5의 MANDATORY "green→merge-awaiting" 룰을
> **이 트랙에 한해 의도적으로 override**한다(사용자 결정, audit 기록). 미래 세션 주의:
> Build & Test green 후에도 Status를 `merge-awaiting`으로 바꾸지 말 것. 루트 Registry
> 행에도 `do-not-enqueue` 표기됨.
>
> **주기적 rebase**: main의 유의미한 머지(특히 `workspace/`·`steering/` 데이터 표면 변화)
> 마다 vibeshell을 최신 main 위로 rebase해 디버전스 비용을 상한한다 (critic 라운드 반영).

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | Yes (전체 blocking; 스테이지별 N/A 판정 허용) | Requirements Analysis (2026-06-12, UAQ) |
| Property-Based Testing | Partial (순수 함수/직렬화 라운드트립만 — jsonl 파서, zod 스키마 변환) | Requirements Analysis (2026-06-12, UAQ) |

## Scope
vibeOS(caffeinum/vibeOS) 패턴의 "방향 A"를 autostock에 이식: 레포에 읽기 전용 생성형
대시보드 웹 사이드카 `viz-shell/`을 추가한다.

1. **Next.js 사이드카 앱** — `steering/snapshot`, `logs/`(journal/turn/equity/trades),
   lessons, signals 산출물을 **읽기 전용 tRPC 라우터**로 노출. Python 데몬 **무변경**
   (파일 직접 읽기, 순수 additive).
2. **채팅 패널 → Claude Code SDK `query()`** — 앱 자신의 `generated/` 디렉토리만 편집
   허용. vibeOS와 달리 `bypassPermissions` 금지, terminal류 라우터 없음.
3. **Next.js dev 서버 HMR**이 생성된 뷰를 즉시 반영 (반응성 계층).
4. **쓰기/스티어링 경로는 기존 operator-console에 그대로** — viz-shell은 순수 읽기 전용.

참고 분석: vibeOS 백엔드 코드 조사 완료(2026-06-11 대화) — 핵심 = 영구 dev 모드 +
인프로세스 Claude Code SDK가 자기 소스 편집 + HMR이 렌더링 엔진. 관련 메모리:
[[opentui-zorder-hittest]] (기존 TUI는 별개 표면), [[worktree-gate-hook]].

## Merge Risk Notes
> 트랙이 merge 후보로 전환 시 작성. (장기 브랜치 — Merge Policy 섹션 참조)

- **공유 파일 (주의)**: 거의 없음 예상 — 신규 `viz-shell/` 디렉토리가 대부분.
  루트 `.gitignore`, `README.md`, `scripts/` 보조 정도.
- **API/시그니처 변경**: 없음 (Python 데몬 무변경 원칙).
- **알려진 동시 변경 (critic 라운드 갱신, 2026-06-12)**: F71·F72는 **이미 main에 머지됨**
  (F71→fdfc041, F72→7b4b409, 둘 다 2026-06-12; R8도 머지 — equity 생산자는
  `src/agent/logs/equity.py`). worktree 분기는 트랙 생성 시점 기록(76ff7b6)이 아니라
  **그 시점의 최신 main**에서 한다. F72가 추가한 `workspace/screening/` 표면은 후속
  확장 시 기존 계약 재사용.

## Stage Progress

### 🔵 INCEPTION PHASE
- [x] Workspace Detection — brownfield, CodeKB 존재(stale: ec2875c vs HEAD 76ff7b6, 근사 컨텍스트로 사용)
- [x] Reverse Engineering — SKIP (CodeKB baseline; 신규 디렉토리 + 파일 읽기 전용 소비)
- [x] Requirements Analysis — standard, 2026-06-12 승인 (`inception/requirements/requirements.md`)
- [x] User Stories — SKIP (운영자=개발자 본인 1명)
- [x] Workflow Planning — `inception/plans/execution-plan.md` 승인 (2026-06-12, critic 반영판)
- [x] Application Design — 승인 (2026-06-13) — `inception/application-design/` 5문서, UAQ 3결정(단일 세션/거부+표시/도구 요약)
- [ ] Units Generation — SKIP (단일 유닛)

### 🟢 CONSTRUCTION PHASE (단일 유닛: viz-shell)
- [x] Functional Design — 승인 (2026-06-13) — 4문서 (`construction/viz-shell/functional-design/`); 추가 지침: UI 깔끔/무버그/reformable
- [ ] NFR Requirements — SKIP (requirements NFR-1~7로 확정)
- [ ] NFR Design — SKIP (Application Design에 통합)
- [ ] Infrastructure Design — SKIP (로컬 dev 서버 단일 프로세스)
- [x] Code Generation — 승인(2026-06-13). vibeshell 109f631 + code-review 8건 e9c959a. 테스트 108/108 + 라이브 스모크
- [x] Build & Test — ✅ GREEN (tsc 클린 / vitest 108 / next build OK / 경계 테스트 / 라이브 IT). **장기 브랜치 — `active` 유지(merge-awaiting 전환 안 함)**. Post-Merge Guide 작성

### 🟢 후속: 지표 확장 (F83 철회 후 순서 정상화 — 2026-06-14)
> F83(공유 카탈로그)을 critic 검증 후 철회하고, 원래 목표(viz-shell 지표 부족 해소)를
> vibeshell에서 직접. Tier 로드맵은 대화 정리분(Tier 0 공짜 → 1 핵심 → 2 분석 → 3 리서치).
- [x] **Tier 0** (2026-06-14) — snapshot 미사용 필드 노출. 스키마 확장(open_orders/recent_fills/
  round_trip/run_state) + 위젯 4종(RunStateBadge/OpenOrdersTable/RoundTripCard/RecentFills),
  라우터 추가 0. 테스트 110 통과 + 라이브 스모크(API 5 orders/8 fills, 위젯 렌더). 미체결
  브래킷/OCO 가시성 확보(최대 격차 해소).
- [ ] **Tier 1** — decisions/turns/trades (jsonl tail 라우터 추가).
- [ ] **Tier 2** — quality/health/watchlist·regime.
- [ ] **Tier 3** — screening/sentiment/surge/lessons/daily (여력 시).

> ⚠️ **발견(F73 갭, Tier 0 중)**: 사용자가 채팅으로 만든 생성 뷰(`src/generated/
> unrealized-pnl-by-symbol.tsx`)에 타입 에러가 있어 `tsc --noEmit`·`next build`를 깨뜨림.
> 런타임은 ErrorBoundary로 격리되나 **빌드/타입체크 게이트는 generated/를 포함해 오염**.
> dev(HMR) 운영엔 무해. 처리 방안(생성뷰를 tsc/build 스코프에서 제외 등)은 별도 결정 대기.

## Current Status
- **Lifecycle Phase**: CONSTRUCTION 완료 + 후속 지표 확장 진행 중
- **Current Stage**: Tier 0 완료 (지표 확장 후속) — vibeshell, 미커밋→커밋 예정
- **Next Stage**: Tier 1(decisions/turns/trades) 또는 사용자 지시. 장기 브랜치 유지
  (merge-awaiting 전환 안 함). main 유의미 머지마다 vibeshell rebase 권장.

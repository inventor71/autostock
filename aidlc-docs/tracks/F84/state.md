# Track F84 — 모바일 차트 (TradingView Lightweight Charts + SolidJS 래퍼), F79 위 스택

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F84
- **Title**: 모바일 PWA 차트 — TradingView Lightweight Charts(+@dschz/solid-lightweight-charts)로 포지션 시세 + 자산 곡선 (F79 위 추가형)
- **Type**: feature
- **Status**: active  <!-- active → merge-awaiting (Build & Test green) → merged (/ai-dlc-merge) -->
- **Branch**: feat/F84 (TBD)
- **Worktree**: .claude/worktrees/F84 (TBD)
- **Submodule branch**: — (monorepo; operator-console/cli/packages/app)
- **Base commit**: **F79 의존** — feat/F79(3cbf2b4) 위에 스택하거나, F79 머지 후 main 기준 rebase.
  (등록 시점 main = d8ceda3; F79 미머지 상태)
- **Start Date**: 2026-06-14T04:12:18Z

## ⚠️ 의존성 (중요)
이 트랙은 **F79의 뷰에 차트를 얹는다** — `dashboard-view.tsx`(자산 곡선), `detail-views.tsx`
`PositionThesisView`(시세 차트), 그리고 `PositionRow`/리치 모델. **F79가 머지되기 전엔 단독
머지 불가.** 권장 순서: F79 머지 → F84를 main에 rebase → 진행. 또는 feat/F79에 스택해 개발하고
F79와 함께/직후 머지. `/ai-dlc-merge` 큐에서 F79보다 먼저 서지 않도록 관리.

## Extension Configuration
| Extension | Enabled | Mode | Decided At |
|---|---|---|---|
| Security Baseline | Yes | Full (blocking) | Requirements Analysis |
| Property-Based Testing | Yes | Full (blocking) | Requirements Analysis |

> Security: 신규 외부 npm 의존성 도입(SECURITY-10 공급망 — 핀 고정/출처/lockfile). 차트는
> 시세 데이터를 그리므로 데이터 무결성/no-data fail-safe(SECURITY-15). PBT: 시계열 변환
> (소스 bar → 차트 포인트) 라운드트립/불변식.

## Scope
F79 모바일 뷰에 **차트를 추가형으로** 얹는다(대체 아님 — OSS 조사 결론: 풀 스톡 앱은 임베드
부적합, 차트 라이브러리만 채택 가치). 채택: **TradingView Lightweight Charts**(MIT, ~45KB) +
**`@dschz/solid-lightweight-charts`**(SolidJS 선언형 래퍼).

대상:
1. **포지션 상세 시세 차트** — `PositionThesisView`에 캔들/라인(일중 또는 N일). 읽기전용.
2. **홈 자산 곡선** — 대시보드 히어로 아래 equity sparkline/area(일중 또는 누적).
범위 밖: 인디케이터/드로잉 툴, 실시간 틱 스트리밍 차트(후속), 차트 위 주문(범위 밖), 워치리스트.

연관: [[llm-trader-redesign]] (에이전트 결정 시각화 맥락), F79(모바일 뷰), F69(health), F61(시그널).

## Merge Risk Notes
> `merge-awaiting` 전환 시 작성.
- **공유 파일**: `operator-console/cli/packages/app/src/addons/autostock/*`(F79와 동일 디렉터리 —
  dashboard-view/detail-views 수정). **F79와 같은 파일** → 반드시 F79 위 스택/순서 머지.
- **의존성 추가**: `lightweight-charts` + `@dschz/solid-lightweight-charts`(app/package.json + lockfile).
- **알려진 동시 변경**: F79(필수 선행).

## Stage Progress
- [x] Workspace Detection — 브라운필드, RE 스킵(CodeKB)
- [x] Requirements Analysis — Standard (FR-1~6, NFR-1~6)
- [x] User Stories — 스킵 (F79 US 흐름에 흡수; 추가형 단일 표면)
- [~] Workflow Planning — 경량 인라인 (단일 추가 기능, F79 의존)
- [x] Application Design — 컴포넌트/데이터/테마/의존성 설계
- [ ] Units Generation — 스킵 예정(단일 유닛, 작음)
- [ ] Construction (Code Generation) — worktree(F79 스택) 생성 후
- [ ] Build & Test

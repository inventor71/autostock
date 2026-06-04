# Track F55 — 타임라인에 "데이마켓" 세션 표기 추가

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F55
- **Title**: 타임라인에 "데이마켓" 세션 표기 추가 (pre/regular/after 외 누락 세션)
- **Type**: feature
- **Status**: merged → main 5c9166d (2026-06-04)  <!-- Build & Test PASS (rebase 후 85/0) -->
- **Branch**: feat/F55
- **Worktree**: .claude/worktrees/F55
- **Submodule branch**: — (monorepo, post-F35; operator-console/cli TUI 변경 가능성 높음)
- **Base commit**: 6bf1b31
- **Start Date**: 2026-06-04

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | No (Q5=B) | Requirements Analysis |
| Property-Based Testing | No (Q6=C) | Requirements Analysis |

- **Security Baseline**: Disabled — 본 트랙은 TUI 표기(타임라인 밴드) 변경으로 외부 입력/인증/시크릿 처리 없음. 전 규칙 N/A.
- **Property-Based Testing**: Disabled — 시간↔x좌표 투영 경계 계산이 있으나 사용자가 PBT opt-out(C). 기존 예제 기반 단위테스트(timeline-layout.test.ts 패턴)로 커버.

## Scope
현재 타임라인 바(`timeline-bar.tsx` + `timeline-layout.ts`)는 `MarketRule`의 4개 경계
(pre_open/regular_open/regular_close/after_close)에서 파생된 **3개 region** (pre/regular/after)만
표기한다. 사용자가 말하는 "데이마켓" 세션이 누락되어 있다. 정확한 의미(어느 거래소/세션인지)는
Requirements Analysis 질문으로 확정한다.

관련: [[opentui-zorder-hittest]] (F34 라벨 z-order), F25/F45 (timeline market-aware + 12h window).

## Merge Risk Notes
- **공유 파일 (주의)**:
  - `operator-console/cli/packages/tui-trading/src/utils/timeline-layout.ts`
  - `operator-console/cli/packages/tui-trading/src/components/timeline-bar.tsx`
  - `operator-console/cli/packages/tui-trading/src/types.ts` (MarketRule 확장 시)
  - `src/agent/steering/runtime.py` (`_DEFAULT_MARKET_RULE` 확장 시 — 다수 트랙이 만지는 파일)
- **API/시그니처 변경**: MarketRule 필드 추가 시 daemon↔TUI 계약 변경 (monitor.json 스키마)
- **알려진 동시 변경**: F30/F33 (KIS/멀티브로커 — 한국장 세션이 관련될 수 있음)

## Stage Progress
- [x] Workspace Detection
- [x] Requirements Analysis — standard (데이마켓=Alpaca 오버나잇 20:00→04:00 ET 확정)
- [x] User Stories — skip (단일 표기 기능, 사용자 워크플로 단순)
- [x] Workflow Planning — execute=Functional Design/Code Gen/Build&Test; skip=AppDesign/Units/NFR×3/Infra
- [ ] Application Design — skip (새 컴포넌트 없음)
- [ ] Units Generation — skip (단일 유닛)
- [ ] Construction
  - [x] Functional Design — 파생방식(MarketRule 불변), 라벨 DAY/DAY-MKT, 앰버색 확정; artifacts 작성
  - [x] NFR Requirements/Design/Infra — skip
  - [x] Code Generation — Timeline `day` region(2-span) + format/REGION_BG + phaseAt; 데몬 불변(파생). bun test 77 pass
- [x] Build & Test — ✅ 77/0 PASS, typecheck F55 파일 0 에러(잔여 fs/path는 main 동일 pre-existing). merge-awaiting.

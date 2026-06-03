# Track F55 — 타임라인에 "데이마켓" 세션 표기 추가

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F55
- **Title**: 타임라인에 "데이마켓" 세션 표기 추가 (pre/regular/after 외 누락 세션)
- **Type**: feature
- **Status**: active  <!-- active → merge-awaiting (set when Build & Test passes) → merged (by /ai-dlc-merge) -->
- **Branch**: feat/F55
- **Worktree**: .claude/worktrees/F55
- **Submodule branch**: — (monorepo, post-F35; operator-console/cli TUI 변경 가능성 높음)
- **Base commit**: <set at worktree creation>
- **Start Date**: 2026-06-04

## Extension Configuration
- **Security Baseline**: <TBD — Requirements Analysis opt-in>
- **Property-Based Testing**: <TBD — Requirements Analysis opt-in>

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
- [ ] Requirements Analysis — standard (UI/UX + 용어 모호성 → 질문 필요)
- [ ] User Stories — skip (단일 표기 기능, 사용자 워크플로 단순)
- [ ] Workflow Planning
- [ ] Application Design — TBD
- [ ] Units Generation — skip (단일 유닛 예상)
- [ ] Construction (per-unit Code Generation)
  - [ ] Timeline session rendering — <note>
- [ ] Build & Test

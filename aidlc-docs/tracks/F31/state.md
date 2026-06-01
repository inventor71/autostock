# Track F31 — TUI Sidebar Orders 색상 깜박임 버그 수정

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F31
- **Title**: TUI Sidebar Orders 색상 깜박임 버그 수정
- **Type**: bugfix
- **Status**: active
- **Branch**: feat/F31
- **Worktree**: .claude/worktrees/F31
- **Submodule branch**: feat/F31 (operator-console/cli)
- **Base commit**: 1746d6a (parent), 674bdb5 (submodule)
- **Start Date**: 2026-06-01T00:00:00Z

## Extension Configuration
- **Security Baseline**: Enabled (N/A — UI-only 1-line fix, no security surface)
- **Property-Based Testing**: Partial (N/A — UI color fallback, no pure-function change)

## Scope
TUI sidebar에서 orders의 색깔이 최근 추가된 종목에 대해 간헐적으로 하얀색으로 표시되었다가,
refresh 후에 초록(stop)/빨강(stop,entry)으로 정상 표시되는 버그 수정.

**Root cause**: `publish_snapshot()` (5s)가 비보유 종목의 주문에 `current_price`를 PriceBook
cache(12s refresh, 30s TTL)에서 조회하는데, 캐시 미스 시 `null`로 기록됨 → `orderDelta()`가
`undefined` 반환 → sidebar가 `theme().text`(하얀색)로 fallback.

**Fix**: `autostock.tsx:334-336` — `orderDelta()`가 `undefined`일 때 order의 `side` 필드로
색상 결정 (sell→red, buy→green, else→text). fills 섹션의 side-based coloring과 일관됨.

## Stage Progress
- [x] Workspace Detection — Brownfield, reverse engineering artifacts exist
- [x] Requirements Analysis — minimal (root cause identified: PriceBook cache miss → null current_price)
- [x] User Stories — skip (internal bug fix)
- [x] Workflow Planning — minimal (single 1-line fix)
- [x] Application Design — skip
- [x] Units Generation — skip
- [x] Construction (Code Generation)
  - [x] Bug fix — autostock.tsx:334-336 (submodule commit 3e163f8)
- [x] Build & Test — sidebar-format tests 8 pass, typecheck clean

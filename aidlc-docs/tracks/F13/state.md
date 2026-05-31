# Track F13 — Sidebar fills date + section spacing

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F13
- **Title**: Sidebar fills date + blank line between sections
- **Type**: feature
- **Status**: merged (submodule feat/F13 → fork main `aa984da`, pushed; parent gitlink `a7a9ea1`; 2026-05-31)
- **Branch**: feat/F13
- **Worktree**: .claude/worktrees/F13
- **Submodule branch**: feat/F13 (operator-console/cli is touched)
- **Base commit**: e8d99a6
- **Start Date**: 2026-05-31T02:46:06Z

## Extension Configuration
- **Security Baseline**: Enabled — but all rules **N/A** for this track: read-only TUI
  rendering change (no secrets, no auth/risk logic, no IaC, no DB). No new attack surface.
- **Property-Based Testing**: Disabled — pure presentational formatting; covered by a small
  example-based unit test on the date/time formatter if a test harness is wired in the fork.

## Scope
Tiny presentational tweak to the trading sidebar in the opencode fork
(`operator-console/cli/.../sidebar/autostock.tsx`), building on [[console-sidebar-upgrade]]
and F8 (status-rich sidebar):
1. **fills rows show a date**, not just `HH:MM` — currently `hhmm()` renders time only.
2. **One blank line between section blocks** (positions / orders / fills / queued / events)
   for visual separation.

Read-only view; no order authority, no daemon/snapshot schema change expected (`ts` already
carries a full ISO timestamp).

## Decisions (locked)
- **fills date**: show `MM/DD` only when the date changes vs the previous row; same-date
  rows blank-pad the date column (6 spaces = `"MM/DD "`.length) so the time column stays
  aligned. Format: `<datePrefix><HH:MM > <SIDE> <qty> <sym> @<price>`.
- **section spacing**: one blank line before each section header — orders / fills / queued /
  events. `positions` stays directly under the account/round-trip block (no leading blank).
- **mechanism**: pure helpers `mmdd()` + `fillDatePrefix(ts, prevTs)` in `sidebar-format.ts`
  (bun-unit-tested); `marginTop={1}` on the four section header `<text>` nodes (idiomatic
  spacer per `system/session-v2.tsx`). No snapshot/daemon schema change (`ts` already ISO).

## Stage Progress
- [x] Workspace Detection — brownfield, RE artifacts exist → RE skipped
- [x] Requirements Analysis — minimal (2 UI decisions locked above)
- [x] User Stories — skip (no new persona/workflow; pure presentational)
- [x] Workflow Planning — collapsed into single approval gate (trivial change)
- [x] Application Design — skip (no new component/method; in-place render edit)
- [x] Units Generation — skip (single trivial unit)
- [x] Construction (per-unit Code Generation)
  - [x] `sidebar-format.ts` — `mmdd()` + `fillDatePrefix()` pure helpers
  - [x] `sidebar-format.test.ts` — 2 new tests (date change / same-date pad / bad ts)
  - [x] `autostock.tsx` — fills `<For>` index + date prefix; `marginTop={1}` on orders/
        fills/queued/events headers
- [x] Build & Test — `bun test sidebar-format.test.ts` 8 pass / 0 fail; `bun run typecheck`
      19/19 successful (worktree `.claude/worktrees/F13`, submodule branch `feat/F13`)

## Status: construction complete & verified — awaiting commit/merge decision
Submodule changes are on branch `feat/F13` (uncommitted in the worktree). Not yet committed
or merged — per project rule, commit/push only when the user asks; the parent gitlink is
committed only at merge time.

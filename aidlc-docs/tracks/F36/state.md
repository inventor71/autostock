# Track F36 — Timeline: historical turn/intervention markers open "not found"

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F36
- **Title**: Timeline historical markers — clicking a past-date turn/intervention marker fails to resolve detail
- **Type**: feature (bug fix)
- **Status**: active
- **Branch**: feat/F36
- **Worktree**: .claude/worktrees/F36 (recreate fresh off current main — see Base)
- **Submodule branch**: N/A — F35 de-submoduled `operator-console/cli` into a normal in-repo
  dir (monorepo). Single `feat/F36` branch covers the TUI edits; no gitlink/submodule dance.
- **Base commit**: 2253029 (main, post-F35 monorepo merge). *(Was 0f26b48/b26a930 in the
  submodule era — re-baselined 2026-06-03 per [[submodule-merge-workflow]] obsolete / F35.)*
- **Start Date**: 2026-06-03

## Extension Configuration
- **Security Baseline**: Enabled — mostly N/A (read-only TUI file reads, no new secrets/IO surface). SECURITY-03/15 already satisfied by existing read paths.
- **Property-Based Testing**: N/A (bug fix; targeted unit coverage on the lookup/correlation).

## Scope
Bug: on the F25 historical timeline, the markers for a **past ET date** are rendered from the
selected date's session data (`readSessionData` reading `turns.jsonl`/`human_directives.jsonl`),
but the **detail overlays resolve from the LIVE monitor payload**:
- `TurnOverlay` looks up `props.monitor.turns.recent` → historical turn id absent → **"Turn W13 not found"**
  (the screenshot).
- `onInterventionClick` (session route `index.tsx:1153`) looks up `monitor().interventions` →
  historical intervention absent → **silent no-op**.
The two sources of truth diverge for any non-today date.

**Root cause**: `selectedDate`/`pinnedDate` is a local signal inside `TimelineBar`; the parent
route mounts the overlays against live `monitor()` and has no idea which date is pinned.

**Fix direction (to confirm in Requirements):** make the overlays resolve from the **same
selected-date session** the timeline rendered (single source of truth). Decision breakdown for a
historical turn requires reading `decisions.jsonl` (no `turn_id`/`et_date` → correlate by
`[started_at, ts_end]` window, mirroring runtime.py `_correlate_turn`) — scope question for user.

Related: [[opentui-zorder-hittest]] (F34 timeline layer), [[feedback-ui-concretization]].

Key files:
- `operator-console/cli/packages/tui-trading/src/components/turn-overlay.tsx:19` (live-only lookup)
- `operator-console/cli/packages/tui-trading/src/components/timeline-bar.tsx:32` (`pinnedDate` local)
- `operator-console/cli/packages/tui-trading/src/hooks/use-session-data.ts` (`readSessionData`)
- `operator-console/cli/packages/opencode/src/cli/cmd/tui/routes/session/index.tsx:1147,1334,1153`
- `src/agent/steering/runtime.py:755` (`_correlate_turn` — reference algorithm)

## Stage Progress
- [x] Workspace Detection — brownfield, RE artifacts exist (reuse).
- [x] Requirements Analysis — APPROVED (Q1 full-parity historical turn overlay, Q2 fix intervention silent-failure). Doc: `inception/requirements/F36-timeline-historical-overlay.md`.
- [x] User Stories — SKIP (bug fix, no new persona/workflow).
- [x] Workflow Planning — single unit; design folded into requirements/plan.
- [x] Application Design — SKIP (no new components; wiring fix).
- [x] Units Generation — SKIP (single unit).
- [~] Construction (per-unit Code Generation) — code+tests DONE, at completion gate.
  - [~] timeline-historical-overlay-fix — re-baselined to monorepo (worktree off main `2253029`, no submodule dance).
    - Plan: `construction/plans/F36-code-generation-plan.md`. Steps 0–6 [x]; Step 7 (live verify + critic + commit) pending.
    - Changed (worktree feat/F36): `use-session-data.ts` (SessionData.decisions + historical `decisions.jsonl` restore + `correlateTurnId` mirroring runtime.py `_correlate_turn`); `types.ts` OverlayState (turn+decisions, dropped turnId); `use-overlay.ts` `openTurn(turn,decisions)`; `turn-overlay.tsx` props from selected-date session (no live monitor lookup → "not found" gone); `timeline-bar.tsx` click callbacks carry full turn+decisions / iv (incl. F34 label-cell path); `index.tsx` wiring + mount (intervention live `find` removed).
    - Verify: `tsgo --noEmit` 0 errors; new `test/session-data.test.ts` → bun test 35 pass / 0 fail.
    - Step 7 docker-verify prep DONE: `.env.test` provisioned; `scripts/seed_timeline.py` (NEW, reusable timeline seeder — turns + decisions w/o turn_id + interventions, `--days N` for consecutive days, per-date deterministic time/turn variation, correlation preserved). Runbook in plan Step 7.
    - **Flicker fix (live-verified working):** markers were N moving `position:absolute` boxes (`<For>`); the live terminal renderer's per-cell damage tracking dropped them on date change → flicker (the composed buffer was always correct, so buffer-level tests couldn't see it — proven via @opentui/core TestRenderer). Fixed by composing the whole MarkerRow into ONE `<text>` of styled spans (the TickRow/band pattern that never flickers) + single-row click hit-test (evt.x→column→entity). Also kept: historical session/layout decoupled from monitor-poll churn, width memo. User confirmed: markers stable + overlays (summary/decisions, intervention) work on past dates.
    - **F36 core + flicker: DONE & user-verified.** Debug instrumentation (F36_DEBUG/f36log) stripped.
    - **critic pass (isolated subagent) DONE** — verified evt.x==column click mapping SAFE (timeline at screen x=0, opentui MouseEvent.x is absolute col; no live-path/intervention/off-by-one regression). Findings reflected: (1) naive decision-ts tz handling = project-wide convention (recordEtDate ≡ Python compute_et_date, machine-local→ET; consistent co-located) — clarifying comments added (use-session-data.ts, timeline-bar.tsx); (2) off-window edge-column collision = pre-existing LOW (paint/click mutually consistent, no wrong-target) — noted; (3) evt.x footgun guard comment added for future left-padding. No logic changes needed. tsgo 0 errors, 35 tests green.
    - Remaining: **commit `feat/F36`** (awaiting explicit approval).
- [ ] Build & Test

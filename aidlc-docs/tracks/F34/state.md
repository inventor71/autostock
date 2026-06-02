# Track F34 — 타임라인 라벨(OPEN/PRE/AFT)이 마커에 가려지는 z-order 수정

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F34
- **Title**: 타임라인 top bar의 OPEN/PRE/AFT 라벨을 마커 위로 올림 (라벨 글자가 마커에 가려지지 않게, 가려진 마커도 클릭 유지)
- **Type**: feature (UI fix)
- **Status**: merged (2026-06-02)
- **Branch**: feat/F34 → main `a366545` (ff)
- **Worktree**: .claude/worktrees/F34 (removed at merge)
- **Submodule branch**: feat/F34 → fork main `43423df` (pushed origin), parent gitlink bumped
- **Base commit**: 378a98b (parent) / submodule 66c6edc (main)
- **Start Date**: 2026-06-01T16:41:21Z

## Extension Configuration
- **Security Baseline**: Enabled — but **all rules N/A** for this change (pure client-side TUI
  rendering/z-order; no secrets, no auth, no risk/order path, no IaC, no error-handling surface).
- **Property-Based Testing**: Enabled (Partial) — **N/A here**; the change is presentational. The
  only pure logic added is a label/marker column-overlap helper, covered by example tests in the
  existing `timeline-layout.test.ts` style (no Hypothesis property needed).

## Scope
**Problem (confirmed in code):** In `packages/tui-trading/src/components/timeline-bar.tsx`,
`MarkerRow` paints in DOM/paint order: region band (which embeds the `PRE`/`OPEN`/`AFT` labels via
`bandText`) → boundary `│` → **turn markers** → intervention markers → now `┃`. Because turn/
intervention markers are painted *after* the band, a marker sitting on a label-letter column
**occludes that letter** (e.g. a turn marker at market-open hides the `O` of `OPEN`).

**Goal (user spec):** Re-layer so the label letters render *on top of* the markers:
`(글자 + 투명배경) > (마커) > (타임라인 배경)`. The marker glyph hidden behind a letter is
acceptable (intentional). **The cell under a label letter must remain clickable as the marker.**

**Framework constraint (verified against `@opentui/core@0.2.16`):** mouse dispatch uses a native
`checkHit(x,y)` that returns the single **topmost-painted** renderable at a cell; the event then
**bubbles to parents, not siblings** (`Renderable.processMouseEvent` → `this.parent`). There is no
`pointerEvents:none`/click-through flag on `Renderable`. ⇒ A naive "label box painted on top" would
**steal the click** from the marker box beneath it (bubbles to `MarkerRow`, never to the sibling
marker). So preserving "click the marker behind the letter" requires **click forwarding** at the
label-overlay layer (resolve click x → marker/intervention under that column → call its handler).

## Stage Progress
- [x] Workspace Detection — brownfield, RE artifacts exist (reused). New distinct request (not a resume).
- [x] Requirements Analysis — **minimal depth** (clear, well-specified request). Doc:
      `aidlc-docs/tracks/F34/requirements.md`. **APPROVED 2026-06-01 ("진행")** after /critic
      feasibility re-check + user z-order clarification (text-only topmost; markers/cursor stay above `│`).
- [ ] User Stories — SKIP (single-operator presentational fix; workflow captured as FRs).
- [ ] Workflow Planning — fold into the requirements/plan gate (single small unit).
- [ ] Application Design — SKIP (no new components/services; one component edit).
- [ ] Units Generation — SKIP (single cohesive unit).
- [x] Construction (per-unit Code Generation) — **DONE** 2026-06-01 (worktree feat/F34, submodule feat/F34)
  - [x] Unit `timeline-label-zorder` — implemented in `operator-console/cli`:
    - `utils/timeline-layout.ts`: new pure `labelCells(regions, barWidth, shortOf)` + `LabelCell`
      (mirrors old `bandText` placement: label one col in from region x0, shown when width ≥ len+2).
    - `components/timeline-bar.tsx`: `bandText` → **dashes only** (band = bottom background); added a
      **topmost transparent per-cell label overlay** (`<For each={labelCells(...)}>`) painted last, so
      PRE/OPEN/AFT sit above markers AND the now `┃` cursor. Each label cell forwards clicks to the
      topmost marker/intervention under its (render-known) column — hidden marker stays clickable;
      anchor uses `evt.x ?? col` (matches direct handlers); `│`/markers/cursor order unchanged.
    - Diff: 3 files, +131/−8.
- [x] Build & Test — **DONE** 2026-06-01.
  - `bun test packages/tui-trading/test/timeline-layout.test.ts` → **26 pass / 0 fail** (5 new `labelCells` tests).
  - `bun run typecheck` (turbo) → **19/19 ✓**; `@tui-trading/core` is typechecked transitively via
    `opencode` (it has no own typecheck script) and `opencode:typecheck` passed.
  - The 8 `fs`/`path` errors from a *standalone* `tsgo -p tui-trading` are **pre-existing** (confirmed
    by stashing my changes → identical 8 errors on base 66c6edc; all in untouched `hooks/*` files;
    they only surface outside turbo's project-reference resolution). None in my edited files.
- [x] **Merged 2026-06-02.** User verified visually in docker-verify `attach` (seeded label-overlap
      probes confirmed letters readable on top + hidden marker clickable). Submodule feat/F34 → fork
      main `43423df` (pushed) → parent gitlink + seed probe committed `a366545` → ff-merged to main →
      main-tree submodule synced. Worktree + feat/F34 branches removed.

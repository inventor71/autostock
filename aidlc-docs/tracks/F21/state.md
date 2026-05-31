# Track F21 — structured MCP order arg robustness (fail-fast pre-queue + omit-optional guidance)

> Per-track state. Single writer = this track's worktree session. See [[f9-gated-alpaca-orders]].

## Track Info
- **Track ID**: F21
- **Title**: Harden all 3 structured MCP tools (`place_stock_order`, `close_position`, `close_all_positions`) against junk/placeholder args + validate before queue
- **Type**: fix (F9 follow-up — robustness, scope expanded 2026-05-31)
- **Status**: merged (2026-05-31, commit 0ed7044→merge to main)
- **Branch**: feat/F21 (worktree at construction)
- **Worktree**: (TBD)
- **Submodule branch**: — (parent repo: `src/agent/steering/commands.py` + `operator-console/src/mcp-server.ts`)
- **Base commit**: 79df84a (main)
- **Start Date**: 2026-05-31

## Problem (observed live)
A weak console model (GPT-5.5 Fast) filled OPTIONAL fields with placeholder `0.01` and set BOTH
qty and notional on `place_stock_order`. Because the market was closed, `_v_place_order` **queued
it BEFORE structural validation** (`_order_from_place_args` runs only after the market-open check),
so it reported "deferred (접수)" — but at next open the gate **rejected** it. Same queue-before-
validate pattern exists in `_v_close_position` and `_v_close_all`.

## Scope (expanded 2026-05-31 — user decision)
All 3 structured MCP tools with off-hours queuing: `place_stock_order`, `close_position`, `close_all_positions`.
Deterministic shorthand (`/sell`, `/flatten`, etc.) excluded — parser validates syntax.

## Policy Decisions (Requirements Analysis, 2026-05-31)
- **P1**: Degenerate optionals → **Hard-reject + 이유** (not sanitize). 0/0.01 등 명백한 placeholder는 즉시 거부.
- **P2**: Pre-queue 검증 → **구조 검증만** (live price 불필요한 것). 가격 대비 sanity는 개장 드레인 시.
- **P3**: qty+notional both-set → **Hard-reject 유지** ("specify either qty or notional, not both").
- **P4**: L3 `_order_from_place_args`의 FR-7 로직 → **삭제** (L1 zod `.refine()`으로 이동). 가격 계산만 남김.
- **Architecture**: 3-layer (L1 zod `.refine()` 동기 → L2 `handleStructured` degenerate → L3 daemon 가격만). Alpaca MCP 동기 패턴 채택.

## Extension Configuration
- **Security Baseline**: Enabled (inherit project-wide). Applicable: SECURITY-15 (fail-closed validation).
- **Property-Based Testing**: Partial (inherit project-wide). Applicable: PBT-02/03 (structural validation round-trip, degenerate-field rejection invariants).

## Stage Progress
- [x] Workspace Detection — reused (brownfield, existing project)
- [x] Reverse Engineering — reused (artifacts exist)
- [x] Requirements Analysis — complete 2026-05-31 (approved). `requirements/requirements.md`
- [x] User Stories — SKIP (bug fix, no personas, no UX change)
- [x] Workflow Planning — complete 2026-05-31 (approved). `plans/execution-plan.md`
- [x] Application Design — SKIP (within existing component boundaries)
- [x] Units Generation — SKIP (single cohesive unit)
- [x] Construction:
  - [x] Functional Design — SKIP (validation rules fully specified in requirements; mechanical translation)
  - [x] NFR Requirements — SKIP (0 new deps; zod `.refine()` built-in)
  - [x] NFR Design — SKIP (no new concurrency/security patterns)
  - [x] Infrastructure Design — SKIP (local daemon, no cloud infra)
  - [x] Code Generation — complete 2026-05-31. `plans/code-generation-plan.md`
  - [x] Build and Test — complete 2026-05-31. `build-and-test/build-and-test-summary.md`

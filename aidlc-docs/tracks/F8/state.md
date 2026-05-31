# Track F8 — Console Sidebar status.py-rich Data & Color

> Per-track state. **Single writer = this track's worktree session.** Root `aidlc-state.md` =
> registry only. Pre-partition detail for F8 also exists in the archived section of root
> `aidlc-state.md` (added before the M1 partition rule landed); this file is now authoritative.
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F8
- **Title**: Console Sidebar — bring scripts/status.py-level data + color into the operator-console sidebar
- **Type**: feature
- **Status**: merged
- **Branch**: feat/console-sidebar-status-rich
- **Worktree**: .claude/worktrees/sidebar-status-rich
- **Submodule branch**: feat/console-sidebar-status-rich (operator-console/cli)
- **Base commit**: 631ec6e (parent), submodule base 576b63c
- **Start Date**: 2026-05-31

## Extension Configuration
- **Security Baseline**: Enabled — applicable SECURITY-03 (no secrets in snapshot/cache — prices/qty/symbols only), SECURITY-15 (price & fills fetch fail-closed). Others N/A (local daemon/TUI, no web/db/auth/IaC).
- **Property-Based Testing**: Partial — pure derivations (pnl%/Δ%/order role/recent_fills sort); Hypothesis (dev). Console derivations bun-tested instead.

## Scope
Enrich the F4/F6 operator-console sidebar (`autostock.tsx`) to `scripts/status.py` richness +
status.py-style green/red+▲▼ color. Built on [[console-sidebar-upgrade]] (F6). Console stays
read-only (`snapshot.json` only, NFR-1); only the daemon's `publish_snapshot` is extended.
- Holdings: current price + signed P&L $/%, row colored by P&L sign.
- Resting orders: role (entry/stop/take) + trigger + Δ-to-trigger %, colored by Δ.
- Recent fills block (time·side·qty·sym·price), colored by side.
- Account: + invested.
- Width floor 24→36; wrapMode="word" rows expand on drag.
Cadence LOCKED (defaults): publish 5s / poll 1.5s; PriceBook slow job 12s + 30s TTL (non-held
order symbols only); recent_fills 45s. 0 new runtime deps.

Docs: requirements `aidlc-docs/inception/requirements/console-sidebar-status-rich.md`; exec plan
`aidlc-docs/inception/plans/f8-execution-plan.md`; construction docs
`aidlc-docs/construction/console-sidebar-status-rich/` + code-gen plan
`aidlc-docs/construction/plans/f8-code-generation-plan.md`.

## Stage Progress
- [x] Workspace Detection — reused (brownfield).
- [x] Reverse Engineering — reused (artifacts exist).
- [x] Requirements Analysis (Standard) — **APPROVED** 2026-05-31. Cadence locked (defaults).
- [x] User Stories — **SKIP** (single-operator tool; FR-1..6 capture workflows; F2–F7 precedent).
- [x] Workflow Planning — **APPROVED** 2026-05-31. Single unit `console-sidebar-status-rich`.
- [x] Application Design — **SKIP** (→ folded into Functional Design).
- [x] Units Generation — **SKIP** (single unit).
- [x] Functional Design (light) — COMPLETE & APPROVED 2026-05-31 (4 artifacts).
- [x] NFR Requirements (minimal) — COMPLETE (0 new deps).
- [x] NFR Design — COMPLETE (PriceBook 12s/30s-TTL, recent_fills 45s, single worker, width floor).
- [x] Infrastructure Design — **SKIP** (local daemon/TUI).
- [x] Code Generation Part 1 (plan) — APPROVED 2026-05-31.
- [x] Code Generation Part 2 (build) — **COMPLETE & verified** 2026-05-31.
  - Parent commit `6c66a1f` (daemon Python + tests + submodule pin); submodule commit `8fcb1ca` (TS sidebar).
  - **Python 371 passed / 0 failed** (venv/python3). **bun 6 pass / 0 fail** (sidebar-format.test.ts). 0 new deps.
  - Daemon: `get_latest_prices` broker port (base no-op + Alpaca StockHistoricalDataClient); `publish_snapshot`
    additive (positions price/mv/pnl, orders side/order_type/current_price, account invested, recent_fills);
    `refresh_order_prices` (12s, PriceBook 30s TTL) + `refresh_recent_fills` (45s) worker jobs.
  - Console: `sidebar-format.ts` (pure orderRole/orderTrigger/orderDelta/pnlPct/fmtPct/fmtPrice) +
    `autostock.tsx` 4-block render (whole-row green/red+▲▼; OpenTUI has no inline color span; wrapMode=word;
    hide-when-absent) + width floor 24→36 in `routes/session/sidebar-width.ts`.
  - **NOT merged/pushed.**
- [x] Build & Test — **COMPLETE** 2026-05-31. Docs `aidlc-docs/construction/build-and-test/console-sidebar-status-rich/build-and-test-summary.md`.
  Python full **371 passed / 0 failed**, bun **6 pass / 0 fail**, 0 new deps. Security SECURITY-03/-15/-11 met. tsgo + live R1-3 + merge = pending (user gate).
- [ ] Operations — placeholder (no work).
- [x] **MERGED to main 2026-05-31** — parent `77d5ed9`, submodule fork main `2ac0cda` (both pushed). Post-merge Python 371 green.

## Verification status
- **Daemon side LIVE-VERIFIED in-worktree 2026-05-31** (paper account, read-only, main .env via dotenv):
  `get_latest_prices` returns floats / empty-list short-circuits; `publish_snapshot` populates account.invested,
  positions current_price/market_value/unrealized_pnl, open_orders side/order_type/current_price, recent_fills key.
  Covers R2 + the daemon half of R1.
- **Still only on your machine (needs a real terminal / submodule deps):**
  - Visual TUI render — R1 colors/layout + R3 drag-resize wrap + floor 36 (run `bun dev` in the console).
  - tsgo typecheck of the 3 submodule TS files (`bun install` in `operator-console/cli` first).
  - Merge (submodule branch → fork main + push, then parent gitlink) + push — outward, user gate.

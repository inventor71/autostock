# Track R7 — Broker behavior fixes (BrokerApiBroker: short-side + fail-closed TIF)

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: R7
- **Title**: BrokerApiBroker behavior fixes deferred from R3 (short-side mapping bug + TIF policy)
- **Type**: refactor (behavior change — NOT behavior-preserving)
- **Status**: backlog  <!-- depends on R3 landing first -->
- **Branch**: refactor/R7 (TBD)
- **Worktree**: .claude/worktrees/R7 (TBD)
- **Submodule branch**: — (Python only)
- **Base commit**: TBD — **rebase onto main AFTER R3 merges** (this builds on the shared base)
- **Start Date**: TBD

## Extension Configuration
- **Security Baseline**: Applicable — these touch order side/TIF (trade-affecting). Verify against
  short-sell gates ([[risk-execution-redesign]], F60 ETB gate) and add explicit tests.
- **Property-Based Testing**: Recommended for the side-mapping table.

## Scope (carved out of R3's T3 gate — user chose "preserve in R3, fix here")
1. **T3-1 (bug)**: `BrokerApiBroker.submit_order` maps `BUY_TO_COVER→SELL` (wrong; should be BUY)
   and `SELL_SHORT→SELL`. Adopt the shared/correct `_alpaca_side`. **Behavior change** — a short
   *cover* on the sandbox farm currently sends the wrong side. Likely unexercised (farm shorting),
   but it's a real correctness bug.
2. **T3-2 (tightening)**: `BrokerApiBroker._time_in_force` silently downgrades non-GTC→DAY; align
   to the F9 fail-closed policy (reject unsupported TIF) so the two brokers behave the same.
3. **T3-3 (optional)**: extended_hours/client_order_id/trailing-stop parity for broker_api — only
   if `alpaca.broker.requests` accepts those kwargs (needs an SDK check first; may be infeasible).

## Why separate from R3
R3 is a behavior-preserving restructure (pure T1). Folding these behavior changes in would make the
restructure diff impossible to review as "no behavior change". After R3, the shared
`AlpacaShapedBroker` base makes these fixes a few-line change (flip broker_api's overrides to use
the base's correct defaults) + targeted tests.

## Stage Progress — NOT STARTED (blocked on R3 merge)
- [ ] Stage 1 — Baseline + characterization (lock the CURRENT wrong behavior as a test, then flip it)
- [ ] Stage 2 — Tier ledger (these are the T3 items, now approved-to-change)
- [ ] Stage 3 — Redesign (new correct behavior spec)
- [ ] Stage 4 — Implementation
- [ ] Build & Test

See `inception/refactor/broker-behavior-fixes/` and R3's `2-tier-ledger.md` (T3-1/2/3).

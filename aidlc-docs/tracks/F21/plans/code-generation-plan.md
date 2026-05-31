# F21 Code Generation Plan

> Track: F21 | Unit: `structured-order-arg-robustness` | 2026-05-31 | **ALL STEPS COMPLETE**

## Unit Context
- **Type**: Bug Fix — validation logic relocation (Python → TypeScript zod)
- **Files modified**: 4 (mcp-server.ts, steer-handler.ts, commands.py, test_steering_place_order.py)
- **Test files created**: 1 (f21-validation.test.ts) + additions to steer-handler.test.ts + test_steering_commands.py
- **0 new runtime deps**

## Steps

### Step 0: Create worktree + submodule branch
- [x] `scripts/worktree-setup.sh F21 --ts` → worktree at `.claude/worktrees/F21`, branch `feat/F21`
- [x] Submodule on `feat/F21`, bun install + tsgo ready
- [x] Baseline typecheck: 19 successful, 0 fail

### Step 1: L1 — `place_stock_order` zod `.refine()` chain (`mcp-server.ts`)
- [x] Add `placeOrderShape` + `placeOrderValidator` with `.refine()` chain:
  - qty/notional mutual exclusivity (FR-1.1)
  - qty or notional required (FR-1.2)
  - notional market+day only (FR-1.3)
  - trail_* only for trailing_stop (FR-1.4)
  - qty integer check (FR-1.5)
- [x] Update field `.describe()` strings
- [x] Update tool description with sync-error retry guidance
- [x] Handler runs `placeOrderValidator.safeParse(args)` before `handleStructured`

### Step 2: L1 — `close_position` zod `.refine()` + description tightening (`mcp-server.ts`)
- [x] `symbol`: `z.string().min(1)` (FR-4.1)
- [x] `percentage`: `.gt(0).lte(100)` (was `.positive().max(100)`, FR-4.3)
- [x] `closePositionValidator` with `.refine()` for qty/percentage mutual exclusivity (FR-4.2)
- [x] Field `.describe()` strings updated (FR-4.4)
- [x] Tool description updated

### Step 3: L1 — `close_all_positions` description tightening (`mcp-server.ts`)
- [x] Tool description updated with `cancel_orders` guidance

### Step 4: L2 — degenerate value check (`steer-handler.ts`)
- [x] `isDegenerate(v: unknown): boolean` — ≤ 0.01 for positive numbers
- [x] `validatePlaceOrderArgs()` — checks 7 degenerate fields
- [x] `validateClosePositionArgs()` — checks qty, percentage
- [x] Integrated into `handleStructured` — rejects before `fd.send()`
- [x] All 3 functions exported for testability

### Step 5: L3 — simplify `_order_from_place_args` (`commands.py`)
- [x] Removed FR-7 qty/notional exclusivity check → L1
- [x] Removed notional market+day check → L1
- [x] Removed "qty or notional required" (kept as defense-in-depth safety net)
- [x] Kept: notional→qty conversion, qty floor, qty≤0, BRACKET auto-upgrade, Order construction
- [x] Docstring updated referencing L1 zod `.refine()`

### Step 6: L3 — pre-queue validation for `_v_close_position` (`commands.py`)
- [x] symbol validation before `queue_offhours` branch
- [x] Empty/missing symbol → `_emit(cmd, "rejected", "symbol required")` + return
- [x] Deferred wording: "market closed; queued for next open (position checked at open)"
- [x] Docstring referencing L1 zod validation

### Step 7: L3 — pre-queue validation for `_v_close_all` (`commands.py`)
- [x] `cancel_orders` bool/None check before queue
- [x] Non-bool → `_emit(cmd, "rejected", "cancel_orders must be a boolean")` + return

### Step 8: L3 — update deferred wording (`commands.py`)
- [x] `place_order`: "market closed; queued for next open (size/price validated at open)"
- [x] `close_position`: "market closed; queued for next open (position checked at open)"
- [x] `close_all`: "market closed; queued for next open"

### Step 9: TS unit tests
- [x] `test/f21-validation.test.ts` — 24 tests:
  - `isDegenerate`: 8 tests (0.01, 0, 0.001, 1.0, undefined, null, negative, string)
  - `validatePlaceOrderArgs`: 9 tests (valid qty/notional/bracket, degenerate 6 fields, undefined)
  - `validateClosePositionArgs`: 5 tests (valid 3 patterns, degenerate qty/percentage)
- [x] `test/steer-handler.test.ts` — 3 new integration tests:
  - place_order degenerate reject before file-drop
  - close_position degenerate reject before file-drop
  - close_position valid args still writes

### Step 10: Python test updates
- [x] `test_steering_commands.py` — 6 new F21 tests:
  - close_position rejects empty symbol off-hours
  - close_position rejects missing symbol off-hours
  - close_all rejects non-bool cancel_orders pre-queue
  - place_order valid args pass simplified `_order_from_place_args`
  - place_order notional sizing still works
  - place_order deferred wording updated
- [x] `test_steering_place_order.py` — updated `test_place_order_notional_non_market_rejected` → `_passes_daemon` (notional+limit check moved to L1)

### Step 11: Contract sync + regression
- [x] `bun run typecheck` — 19 successful, 0 fail
- [x] TS tests: 39 pass (f21-validation + steer-handler), 6 pass (contract)
- [x] `python -m pytest tests/ -x -q` — **420 passed, 0 fail**
- [x] Python contract test: 4 passed
- [x] TS contract test: 6 passed
- [x] Addressed FR-7 test failure → updated to reflect L1 relocation

## Completion Summary

| File | Action | Tests |
|------|--------|-------|
| `operator-console/src/mcp-server.ts` | Modified: zod `.refine()` for 3 tools + description tightening | L1 sync validation |
| `operator-console/src/steer-handler.ts` | Modified: L2 degenerate check + handleStructured integration | 24 new TS tests |
| `src/agent/steering/commands.py` | Modified: L3 simplified + pre-queue validation + wording | 6 new Python tests |
| `tests/test_steering_place_order.py` | Modified: 1 test updated for L1 relocation | — |
| `operator-console/test/f21-validation.test.ts` | Created: L1/L2 validation unit tests | 24 tests |
| `operator-console/test/steer-handler.test.ts` | Modified: +3 L2 integration tests | — |
| `tests/test_steering_commands.py` | Modified: +6 F21 tests | — |

**Regression**: 420 Python + 45 TS = 465 tests green. Typecheck clean. Contract sync verified.

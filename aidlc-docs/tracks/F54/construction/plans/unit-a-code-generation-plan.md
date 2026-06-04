# Unit A: Trading Core — Code Generation Plan

> **Track**: F54 / Unit A
> **Phase**: Code Generation Part 1 (Plan)
> **Date**: 2026-06-04
> **0 new runtime dependencies**

## Prerequisites
- [x] Worktree: `git worktree add .claude/worktrees/F54 -b feat/F54` (Part 2 first action)
- [x] Poetry/pip venv: `scripts/worktree-setup.sh F54 --py`

## Implementation Steps

### Step 0: Worktree Setup
- [x] Create worktree: `git worktree add .claude/worktrees/F54 -b feat/F54`
- [x] Setup: `scripts/worktree-setup.sh F54 --py`
- [x] Verify: `python -c "from src.core.types import PositionSide; print('ok')"`

### Step 1: Core Types — `src/core/types.py`
- [x] Add `SELL_SHORT = "sell_short"` to `OrderSide`
- [x] Add `BUY_TO_COVER = "buy_to_cover"` to `OrderSide`
- [x] Add `SELL_SHORT = "SELL_SHORT"` to `Signal`
- [x] Add `BUY_TO_COVER = "BUY_TO_COVER"` to `Signal`
- [x] Verify: `python -c "from src.core.types import OrderSide, Signal; assert OrderSide.SELL_SHORT; assert Signal.SELL_SHORT"`

### Step 2: Core Models — `src/core/models.py`
- [x] Add `side: PositionSide = PositionSide.LONG` to `Position` model
- [x] Fix `Position.update_price()`: invert P&L calc for SHORT side
- [x] Add `from src.core.types import PositionSide` import
- [x] Extend `Order._check_bracket_legs()`: validate short bracket geometry (stop>limit, target<limit for SELL_SHORT/BUY_TO_COVER)
- [x] Add `DecisionAction` to imports if needed for journal changes
- [x] Verify: `python -c "from src.core.models import Position; p=Position(symbol='X',qty=10,avg_entry_price=100,side='short'); p.update_price(90); assert p.unrealized_pnl > 0"`

### Step 3: Journal — `src/agent/journal.py`
- [x] Add `"SELL_SHORT"` and `"BUY_TO_COVER"` to `DecisionAction` Literal
- [x] Verify: type check passes

### Step 4: Risk Manager — `src/risk/manager.py`
- [x] Add import: `PositionSide` from `src.core.types`
- [x] Add `_short_stop_loss_pct`, `_short_take_profit_pct`, etc. as config fallback properties
- [x] Add `_new_shorts_halted` flag + `new_shorts_halted` property
- [x] Extend `update_market_halt()`: add short breaker logic (SPY ≥ +threshold → halt shorts)
- [x] Add `individual_stock_halt_pct` config + stock-level short halt check
- [x] Add `_handle_sell_short()`: short entry gate (circuit breaker, pool, existing position, mandatory stop)
- [x] Add `_handle_buy_to_cover()`: short cover (find short position, partial cover)
- [x] Add `_build_bracket_short()`: inverted bracket builder (stop above, target below)
- [x] Add `_resolve_short_stop()`: short stop resolution (ceiling, ATR-based)
- [x] Add `_simple_sell_short()`: simple short with mandatory stop
- [x] Extend `evaluate_signal()`: route SELL_SHORT/BUY_TO_COVER
- [x] Extend `_receive_human_order()`: route SELL_SHORT/BUY_TO_COVER
- [x] Add `_receive_human_sell_short()`: human short order gate
- [x] Add `_receive_human_buy_to_cover()`: human cover order gate
- [x] Extend `ratchet_stop()`: accept position_side parameter, invert for SHORT
- [x] Extend `check_stop_loss()`: direction-aware stop trigger
- [x] Extend `check_take_profit()`: direction-aware profit trigger
- [x] Update `_resolve_stop()` docstring (long-only, keep as-is)
- [x] Verify: import smoke test

### Step 5: Position Sizer — `src/risk/position_sizer.py`
- [x] Verify `calculate_shares()` works for short stop fractions (stop_frac is positive regardless of direction; math is identical)
- [x] Add docstring for short usage
- [x] No logic changes needed (stop_frac is already absolute percentage)

### Step 6: BaseBroker — `src/execution/base.py`
- [x] Update docstrings to acknowledge SELL_SHORT/BUY_TO_COVER
- [x] No logic changes (abstract methods accept any OrderSide)

### Step 7: AlpacaBroker — `src/execution/brokers/alpaca_broker.py`
- [x] Map `OrderSide.SELL_SHORT → AlpacaSide.SELL_SHORT` in `submit_order()`
- [x] Map `OrderSide.BUY_TO_COVER → AlpacaSide.BUY_TO_COVER` in `submit_order()`
- [x] Preserve `position.side` from Alpaca API response in `get_position()` and `get_all_positions()`
- [x] Update `_to_fill_event()` to recognize `sell_short`/`buy_to_cover` sides
- [x] Verify: import + side mapping logic

### Step 8: SimulatedBroker — `src/execution/brokers/simulated.py`
- [x] Track position side in internal position dict
- [x] Handle SELL_SHORT → open short position
- [x] Handle BUY_TO_COVER → close short position
- [x] Handle auto-flip scenarios (long→short, short→long)
- [x] Update `get_position()` to return Position with side

### Step 9: DecisionExecutor — `src/agent/executor.py`
- [x] Extend `_to_signal()`: map `SELL_SHORT → Signal.SELL_SHORT`, `BUY_TO_COVER → Signal.BUY_TO_COVER`
- [x] Add metadata for short signals (key_levels with inverted semantics)
- [x] Add auto-flip logic in `execute_decision()`: detect LONG+SELL_SHORT → close then short; SHORT+BUY → cover then buy
- [x] Extend `_place_protection()`: direction-aware OCO side (SHORT → BUY_TO_COVER OCO)
- [x] Extend `_adjust_stop()`: pass position_side to ratchet_stop
- [x] Update `_cancel_and_wait()`: works for both sides (no change needed)
- [x] Verify: import smoke test

### Step 10: Risk Exits — `src/risk/exits.py`
- [x] Verify `run_polled_exits()` handles SELL_SHORT/BUY_TO_COVER orders from RiskManager
- [x] No logic changes needed (just passes orders to broker)

### Step 11: Tests — `tests/test_short_risk.py` (NEW)
- [x] PBT: `test_short_pnl_sign_invariant` (Hypothesis) — PBT-03
- [x] PBT: `test_short_stop_ceiling_invariant` (Hypothesis) — PBT-03
- [x] PBT: `test_short_order_round_trip` (Hypothesis) — PBT-02
- [x] Unit: `test_sell_short_rejected_without_stop` — BR-1
- [x] Unit: `test_sell_short_bracket_geometry` — BR-2
- [x] Unit: `test_buy_to_cover_partial` — BR-5
- [x] Unit: `test_auto_flip_long_to_short` — BR-6
- [x] Unit: `test_auto_flip_short_to_long` — BR-6
- [x] Unit: `test_auto_flip_partial_close_aborts` — BR-6
- [x] Unit: `test_short_circuit_breaker_halt` — BR-7
- [x] Unit: `test_individual_stock_10pct_halt` — BR-7
- [x] Unit: `test_short_stop_ratchet_tightens_downward` — BR-4
- [x] Unit: `test_polled_stop_loss_short` — BR-11
- [x] Unit: `test_polled_take_profit_short` — BR-11
- [x] Unit: `test_position_side_preserved_from_alpaca` — BR-10

### Step 12: Regression — Full Test Suite
- [x] Run full test suite: `python -m pytest tests/ -x -q`
- [x] Target: existing ~356 tests green + new Unit A tests green
- [x] Fix any regressions from Position.side default, Order validator changes

### Step 13: Type Check
- [x] Run type checker on changed files
- [x] Fix any type errors from new enum values

## Estimated New Tests: ~15 (PBT + Unit)
## 0 New Runtime Dependencies

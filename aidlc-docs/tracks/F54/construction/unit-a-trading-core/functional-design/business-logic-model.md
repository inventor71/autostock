# Unit A: Trading Core — Business Logic Model

> **Track**: F54 / Unit A
> **Phase**: Functional Design
> **Date**: 2026-06-04

## BLM-1: Signal Routing (RiskManager.evaluate_signal)

**Current**: `BUY → _handle_buy`, `SELL → _handle_sell`, `HOLD → None`.

**New routing**:
```
evaluate_signal(signal, price, portfolio)
├── HOLD          → return None
├── BUY           → _handle_buy(signal, price, portfolio)
├── SELL          → _handle_sell(signal, price, portfolio)
├── SELL_SHORT    → _handle_sell_short(signal, price, portfolio)   ← NEW
└── BUY_TO_COVER  → _handle_buy_to_cover(signal, price, portfolio) ← NEW
```

---

## BLM-2: Short Entry (_handle_sell_short)

Mirrors `_handle_buy` with inverted direction. Flow:

```
_handle_sell_short(signal, price, portfolio)
│
├── 1. Circuit breaker check
│   └── if _new_shorts_halted → log warning, return None
│
├── 2. Position pool check
│   └── if portfolio.position_count >= max_open_positions → log, return None
│
├── 3. Existing position check
│   └── if signal.symbol in portfolio.positions:
│       ├── if position.side == SHORT: "already holding short", return None
│       └── if position.side == LONG:  DEFER to auto-flip (FR-3)
│           return None with metadata ("LONG_HELD") ← executor handles
│
├── 4. Bracket short (if use_bracket_orders)
│   └── _build_bracket_short(signal, price, portfolio)
│       └── if stop resolved → return BRACKET SELL_SHORT order
│       └── if no stop source → REJECT (mandatory stop for shorts, FR-4.1)
│           └── log "short entry requires stop", return None
│
└── 5. Simple short (only if bracket_orders disabled)
    └── _simple_sell_short(signal, price, portfolio)
        └── MUST include stop_loss_price (FR-4.1 mandatory)
```

**Key difference from _handle_buy**: `_handle_buy` falls through to simple market buy when no stop source exists. `_handle_sell_short` **rejects** — shorts MUST have a stop. This is a structural safety gate (NFR-1.1).

---

## BLM-3: Short Bracket Builder (_build_bracket_short)

Mirrors `_build_bracket_buy` with inverted geometry. Flow:

```
_build_bracket_short(signal, price, portfolio)
│
├── 1. Extract levels from signal.metadata["key_levels"]
│   ├── entry: float | None
│   ├── stop: float | None   ← ABOVE entry (inverted)
│   ├── target: float | None ← BELOW entry (inverted)
│   └── atr: float | None
│
├── 2. Entry reference
│   └── entry_ref = entry if entry is not None else price
│
├── 3. Resolve stop (short version)
│   └── _resolve_short_stop(entry_ref, stop, atr)
│       ├── if stop is not None and stop > entry_ref: resolved = stop
│       ├── elif atr is not None: resolved = entry_ref + atr_stop_multiple * atr
│       └── else: return None → REJECT (mandatory stop)
│       ├── ceiling = entry_ref * (1 + max_stop_distance_pct)
│       └── if resolved > ceiling: resolved = ceiling  (cap max risk)
│
├── 4. Size from stop distance
│   └── stop_frac = (resolved_stop - entry_ref) / entry_ref  (positive %)
│   └── shares = position_sizer.calculate_shares(..., stop_loss_pct=stop_frac)
│
├── 5. Resolve target (inverted)
│   └── if target is not None and target < entry_ref: resolved_target = target
│   └── else: resolved_target = entry_ref - default_risk_reward * (resolved_stop - entry_ref)
│       └── guard: target must be > 0 (stock can't go below zero)
│
├── 6. Entry type
│   └── use_limit = entry is not None and entry > price  (SHORT: sell at limit above market)
│
└── 7. Return Order
    └── side=SELL_SHORT, qty=shares, order_class=BRACKET
        stop_loss_price=resolved_stop, take_profit_price=resolved_target
```

**Inverted Geometry Summary**:
| Aspect | Long (BUY) | Short (SELL_SHORT) |
|--------|-----------|-------------------|
| Stop position | Below entry | Above entry |
| Target position | Above entry | Below entry |
| Use limit when | limit < price (buy the dip) | limit > price (sell the rip) |
| RR formula | entry + RR×(entry-stop) | entry - RR×(stop-entry) |
| Stop distance cap | floor = entry×(1-max%) | ceiling = entry×(1+max%) |

---

## BLM-4: Short Cover (_handle_buy_to_cover)

Mirrors `_handle_sell` for closing short positions:

```
_handle_buy_to_cover(signal, price, portfolio)
│
├── 1. Find short position
│   └── position = portfolio.positions.get(signal.symbol)
│   └── if position is None or position.side != SHORT:
│       └── log "no short position", return None
│
├── 2. Cover fraction
│   └── cover_pct = getattr(signal, "sell_pct", 1.0)  (reuse sell_pct field)
│   └── qty = min(round(position.qty * cover_pct, 9), position.qty)
│
└── 3. Return Order
    └── side=BUY_TO_COVER, qty=qty
```

---

## BLM-5: Human Short Order Reception

Extends `RiskManager.receive_human_order()`:

```
receive_human_order(order, portfolio, price, atr, force)
│
├── existing BUY path (unchanged)
├── existing SELL path (unchanged, closes long)
│
├── SELL_SHORT branch ← NEW
│   └── _receive_human_sell_short(order, portfolio, price, atr, force)
│       ├── 1. Circuit breaker: if _new_shorts_halted and not force → BREAKER_HALTED
│       ├── 2. Pool: if position_count >= max and not force → POOL_FULL
│       ├── 3. Already holding short: if symbol in positions and side==SHORT → ALREADY_HELD
│       ├── 4. Holding long: → suggest auto-flip (NEEDS_FLIP)
│       ├── 5. Price sanity (inverted): stop_loss > entry, take_profit < entry
│       ├── 6. Budget clamp: same as buy but stop_frac = (stop-entry)/entry
│       ├── 7. Auto-protect: plain market SELL_SHORT → BRACKET with resolved stop
│       └── 8. MANDATORY STOP: if no stop after auto-protect → reject (NO_STOP)
│
└── BUY_TO_COVER branch ← NEW
    └── _receive_human_buy_to_cover(order, portfolio, price, force)
        ├── 1. Find short position: if none → NO_POSITION
        ├── 2. Cover stop sanity: a cover stop must be ≥ market (or it would trigger immediately)
        └── 3. Clamp qty to held position
```

---

## BLM-6: Auto-Flip (FR-3) — Executor Level

Resides in `DecisionExecutor.execute_decision()`, NOT in RiskManager. RiskManager returns a signal that indicates "I would short but there's a long position." The executor handles the flip:

```
execute_decision(d)  ← modified
│
├── if d.action == "SELL_SHORT":
│   ├── pos = broker.get_position(d.symbol)
│   ├── if pos is not None and pos.side == LONG:
│   │   ├── 1. Close long: execute SELL for position.qty
│   │   │   └── signal = TradeSignal(symbol, Signal.SELL, sell_pct=1.0)
│   │   │   └── order = risk_manager.evaluate_signal(signal, price, portfolio)
│   │   │   └── filled = broker.submit_order(order)
│   │   │   └── if filled.qty == 0: return "error" (close failed, abort flip)
│   │   │
│   │   ├── 2. Re-fetch portfolio (position may be gone now)
│   │   │
│   │   └── 3. Enter short: signal = TradeSignal(symbol, Signal.SELL_SHORT, ...)
│   │       └── order = risk_manager.evaluate_signal(signal, price, portfolio)
│   │       └── filled = broker.submit_order(order)
│   │       └── both outcomes logged separately
│   │
│   └── else: normal short entry (no flip needed)
│
├── if d.action == "BUY":
│   ├── similar auto-flip: short cover → then buy
│   └── ...
```

**Invariant**: Auto-flip is all-or-nothing. If the close fails, the new entry is NOT attempted. Each leg gets its own execution outcome.

---

## BLM-7: Stop Loss / Take Profit Polled Backup

Modified `check_stop_loss()` and `check_take_profit()` to handle both directions:

```
check_stop_loss(portfolio, protected_symbols)
├── for each (symbol, position):
│   ├── skip if symbol in protected_symbols
│   ├── skip if avg_entry_price <= 0
│   │
│   ├── if position.side == LONG:
│   │   └── loss_pct = (avg_entry - current_price) / avg_entry
│   │   └── if loss_pct >= stop_loss_pct → SELL order
│   │
│   └── if position.side == SHORT:
│       └── loss_pct = (current_price - avg_entry) / avg_entry  ← inverted
│       └── if loss_pct >= stop_loss_pct → BUY_TO_COVER order    ← NEW action
│
check_take_profit(portfolio, protected_symbols)
├── for each (symbol, position):
│   ├── if position.side == LONG:
│   │   └── gain_pct = (current_price - avg_entry) / avg_entry
│   │   └── if gain_pct >= take_profit_pct → SELL order
│   │
│   └── if position.side == SHORT:
│       └── gain_pct = (avg_entry - current_price) / avg_entry  ← inverted
│       └── if gain_pct >= take_profit_pct → BUY_TO_COVER order  ← NEW action
```

---

## BLM-8: Short Stop Ratchet

```
ratchet_stop(current_stop, proposed_stop, allow_widen, position_side)
│
├── if position_side == LONG:
│   └── return max(current_stop, proposed_stop)  if not allow_widen else proposed_stop
│       (tighten = raise stop, existing behavior)
│
└── if position_side == SHORT:
    └── return min(current_stop, proposed_stop)  if not allow_widen else proposed_stop
        (tighten = lower stop, inverted from long)
```

---

## BLM-9: Circuit Breaker Extension

```
update_market_halt(spy_change_pct)
│
├── Long breaker (existing):
│   └── _new_buys_halted = spy_change_pct <= market_halt_threshold_pct (-3% default)
│
└── Short breaker (NEW):
    └── _new_shorts_halted = spy_change_pct >= short_market_halt_threshold_pct (+3% default)

Individual stock breaker (NEW, in _handle_sell_short):
├── day_change = (current_price - prev_close) / prev_close
└── if day_change >= 0.10 (10%+): reject short on this symbol
```

---

## BLM-10: Protection Placement Direction Awareness

`DecisionExecutor._place_protection()` modified for short positions:

```
_place_protection(d, label)
│
├── Get position. Determine side.
│
├── If LONG (existing):
│   └── SELL OCO/Bracket with stop below, target above
│
└── If SHORT (NEW):
    └── BUY_TO_COVER OCO/Bracket with stop above, target below
    └── ratchet_stop(..., position_side=SHORT) for ADJUST_STOP on shorts
```

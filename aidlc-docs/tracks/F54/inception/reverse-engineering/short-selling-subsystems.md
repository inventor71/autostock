# Reverse Engineering: Short-Selling Relevant Subsystems

> **Track**: F54 — 숏 포지션 기능
> **Scope**: Focused analysis on order execution, risk management, position tracking,
> agent decision pipeline, and backtesting — subsystems that must change to support shorts.
> **Date**: 2026-06-04

## 1. Business Overview — Current (Long-Only) Transaction Flow

```
Agent (LLM) → Decision(BUY|SELL|HOLD|ADJUST_STOP) → Journal(decisions.jsonl)
  → DecisionExecutor → RiskManager.evaluate_signal(TradeSignal) → Order → Broker.submit_order()
  → Alpaca/Simulated → FilledOrder
```

All transactions assume LONG positions:
- **BUY** = open a new long position
- **SELL** = close (or reduce) an existing long position
- **HOLD** = maintain long + place/ratchet protective stop
- **ADJUST_STOP** = tighten the protective stop on a long

No short path exists anywhere in this chain.

## 2. Architecture — Affected Subsystems

### 2.1 Core Types (`src/core/types.py`)
- **`PositionSide`** (LONG/SHORT) — **exists but is unused**. Defined at L129-131, nowhere referenced in models.
- **`OrderSide`** (BUY/SELL) — no SELL_SHORT / BUY_TO_COVER.
- **`Signal`** (BUY/SELL/HOLD) — no SELL_SHORT / BUY_TO_COVER signals.
- **`DecisionAction`** (`src/agent/journal.py:24`) — Literal["BUY", "SELL", "HOLD", "ADJUST_STOP"]. No short actions.

### 2.2 Core Models (`src/core/models.py`)
- **`Position`** — **NO `side` field**. All positions are implicitly long. `qty` is always positive.
  `avg_entry_price`, `unrealized_pnl`, `market_value`, `cost_basis` all assume long-only.
  `update_price()`: `market_value = qty * price` (works for both but P&L sign differs).
- **`Order`** — carries `side: OrderSide` (BUY/SELL). Protective leg semantics (`stop_loss_price` < entry, `take_profit_price` > entry) are hardcoded for longs in validator and all call sites.
- **`PortfolioState`** — `positions: dict[str, Position]` keyed by symbol only (no side). A single symbol can't be both long and short simultaneously.

### 2.3 Risk Manager (`src/risk/manager.py`) — HEAVILY LONG-ONLY
Critical methods and their long assumptions:

| Method | Long Assumption | What Must Change |
|--------|----------------|-----------------|
| `evaluate_signal()` L111-128 | BUY→long entry, SELL→long exit | Add SELL_SHORT→short entry, BUY_TO_COVER→short exit |
| `_handle_buy()` L130-159 | "already holding" skip, circuit breaker for "new buys" | Short entry must check for existing short position, not long |
| `_build_bracket_buy()` L161-221 | Stop BELOW entry, target ABOVE entry | Short bracket: stop ABOVE entry, target BELOW entry |
| `_resolve_stop()` L223-243 | `stop < entry`, floor = `entry * (1 - max_stop_distance_pct)` | Short: `stop > entry`, ceiling = `entry * (1 + max_stop_distance_pct)` |
| `_simple_buy()` L245-272 | `side=OrderSide.BUY` hardcoded | Parameterize by direction |
| `_handle_sell()` L274-311 | "No position → skip" | Short cover: must find short position, not long |
| `_receive_human_buy()` L349-448 | Price sanity: stop_loss < entry, take_profit > entry | Flip for shorts |
| `_receive_human_sell()` L450-478 | Sell stop must be at/below market for longs | Short cover stop must be at/above market |
| `ratchet_stop()` L483-493 | Only tightens upward (`max(current, proposed)`) | Short ratchet: tighten downward (`min(current, proposed)`) |
| `check_stop_loss()` L498-527 | `(entry - current) / entry >= stop_loss_pct` | Short: `(current - entry) / entry >= stop_loss_pct` |
| `check_take_profit()` L529-554 | `(current - entry) / entry >= take_profit_pct` | Short: `(entry - current) / entry >= take_profit_pct` |
| `update_market_halt()` L87-102 | "halt new buys" only | Add "halt new shorts" (separate breaker or unified) |
| `new_buys_halted` property L104-106 | Buys only | Add `new_shorts_halted` or generalize |

### 2.4 Position Sizer (`src/risk/position_sizer.py`)
- `calculate_shares()` L19-71: Generic enough to work for both directions (takes `price`, `stop_loss_pct`, `portfolio`). Returns `int` (whole shares). The stop_loss_pct semantic differs (long: % below entry, short: % above entry) but the math is the same — the caller just computes the right percentage.

### 2.5 Execution Layer
- **`BaseBroker`** (`src/execution/base.py`): Abstract — `submit_order(Order)` + `get_position(symbol)`. No direction awareness. A symbol can only have ONE position (get_position returns single Position).
- **`AlpacaBroker`** (`src/execution/brokers/alpaca_broker.py`): Maps `OrderSide.BUY→AlpacaSide.BUY`, `OrderSide.SELL→AlpacaSide.SELL`. Alpaca's API supports `sell_short` and `buy_to_cover` sides natively. Currently `get_position()` returns a Position with no side field — Alpaca's API DOES return `side: "long" | "short"` on positions but we drop it.
- **`SimulatedBroker`** (`src/execution/brokers/simulated.py`): Used by backtests. Likely also long-only.

### 2.6 Agent Pipeline
- **`DecisionExecutor`** (`src/agent/executor.py`): `_to_signal()` L260-273 maps `action=="BUY" → Signal.BUY`, `action=="SELL" → Signal.SELL`. Add SELL_SHORT/BUY_TO_COVER mapping.
- **`Journal`** (`src/agent/journal.py`): `Decision.action` Literal needs expansion.
- **`Prompts`** (`src/agent/prompts.py`): All prompts mention only BUY/SELL/HOLD. Need short-selling context.
- **`Agent Tools`** (`src/agent/tools/market.py`): `shortRatio`, `shortPercentOfFloat` are in the fundamentals output but no dedicated short-interest analysis tool exists.

### 2.7 Backtest Engine (`src/backtest/engine.py`)
- Uses `SimulatedBroker` + `RiskManager`. Long-only by inheritance.

### 2.8 Strategy Layer (`src/strategy/`)
- `BaseStrategy` — generates `TradeSignal` with `Signal.BUY|SELL|HOLD`. All strategies are long-only.

## 3. Component Inventory — Files That Must Change

### Core (must change)
| File | Change |
|------|--------|
| `src/core/types.py` | Add `SELL_SHORT`, `BUY_TO_COVER` to `OrderSide`; add `SELL_SHORT`, `BUY_TO_COVER` to `Signal` |
| `src/core/models.py` | Add `side: PositionSide` to `Position`; update `update_price()` P&L calc for shorts |
| `src/agent/journal.py` | Add `SELL_SHORT`, `BUY_TO_COVER` to `DecisionAction` |

### Risk (major changes)
| File | Change |
|------|--------|
| `src/risk/manager.py` | Full short support: `_handle_sell_short()`, `_handle_buy_to_cover()`, inverted bracket/stop/target logic, inverted ratchet, inverted polled exits, direction-aware price sanity |
| `src/risk/position_sizer.py` | Minor: ensure `calculate_shares()` works for short entries (it should, but verify) |

### Execution (changes needed)
| File | Change |
|------|--------|
| `src/execution/base.py` | `get_position(symbol)` → may need direction awareness; or keep single-position-per-symbol |
| `src/execution/brokers/alpaca_broker.py` | Map `SELL_SHORT→AlpacaSide.SELL_SHORT`, `BUY_TO_COVER→AlpacaSide.BUY_TO_COVER`; preserve position `side` from Alpaca API |
| `src/execution/brokers/simulated.py` | Add short position tracking |

### Agent (changes needed)
| File | Change |
|------|--------|
| `src/agent/executor.py` | Map new action types to signals; direction-aware protection placement |
| `src/agent/prompts.py` | Add short-selling context, short analysis prompts |
| `src/agent/tools/market.py` | Add short-interest / borrow-fee analysis tool |
| `src/agent/orchestrator.py` | Handle short positions in held symbols |

### Backtest (changes needed)
| File | Change |
|------|--------|
| `src/backtest/engine.py` | Short-aware order processing |

### Strategy (changes needed)
| File | Change |
|------|--------|
| `src/strategy/base.py` | Extend signal types |
| `src/strategy/llm/llm_strategy.py` | Prompt for short decisions |
| Various technical strategies | May need short signal support |

## 4. Key Design Decisions (to be resolved in Requirements Analysis)

1. **Single position per symbol or long+short simultaneously?** Currently one Position per symbol. Allowing both long and short on the same symbol simultaneously is complex (hedge accounting). Simpler: only one position per symbol, direction determined by `Position.side`.

2. **Short entry mechanism**: SELL_SHORT to open, BUY_TO_COVER to close — mirror of BUY/SELL. Or reuse SELL for both long-exit and short-entry with context from position state?

3. **Bracket order inversion**: Short brackets need stop ABOVE entry and target BELOW entry. The Alpaca API supports this (bracket with sell_short side).

4. **Market-wide short halt**: Separate circuit breaker for shorts, or unified "no new positions" breaker?

5. **Short-specific analysis**: What data does the agent need? Short interest, borrow rate, days-to-cover, short squeeze risk?

6. **Backtest support**: Full parity with long backtesting including short-specific metrics?

## 5. Technology Stack
- **Existing**: Python 3.11+, pydantic, loguru, alpaca-py, pandas, APScheduler
- **No new dependencies anticipated** — alpaca-py natively supports short selling
- **Alpaca Paper Account**: Supports short selling in paper trading (T+0, no locate requirement in paper)

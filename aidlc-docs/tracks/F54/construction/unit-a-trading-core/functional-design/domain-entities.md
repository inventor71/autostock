# Unit A: Trading Core — Domain Entities

> **Track**: F54 / Unit A
> **Phase**: Functional Design
> **Date**: 2026-06-04

## New & Modified Entities

### E1: PositionSide (existing, now applied)
`src/core/types.py:129-131`

```
PositionSide
├── LONG  = "long"   (existing)
└── SHORT = "short"  (existing, now wired into Position)
```

**Change**: Previously defined but unused. Now referenced by `Position.side`.

---

### E2: Position (modified)
`src/core/models.py:106-121`

```
Position
├── symbol: str
├── qty: float
├── side: PositionSide = PositionSide.LONG   ← NEW
├── avg_entry_price: float
├── current_price: float = 0.0
├── unrealized_pnl: float = 0.0
├── market_value: float = 0.0
│
├── cost_basis: property → qty * avg_entry_price  (unchanged)
├── update_price(price) → modifies unrealized_pnl, market_value
│   ├── LONG:  unrealized_pnl = market_value - cost_basis  (existing)
│   └── SHORT: unrealized_pnl = cost_basis - market_value  (NEW — sign inversion)
```

**Invariant**: `unrealized_pnl` sign matches profit/loss convention:
- LONG: price↑ → positive P&L
- SHORT: price↓ → positive P&L

---

### E3: OrderSide (extended)
`src/core/types.py:12-14`

```
OrderSide
├── BUY         = "buy"          (existing)
├── SELL        = "sell"         (existing)
├── SELL_SHORT  = "sell_short"   ← NEW
└── BUY_TO_COVER = "buy_to_cover" ← NEW
```

**Inherited semantics**:
- `BUY` → open long / cover short (direction determined by context in executor)
- `SELL` → close long / open short (direction determined by context in executor)
- `SELL_SHORT` → open short (explicit)
- `BUY_TO_COVER` → close short (explicit)

---

### E4: Signal (extended)
`src/core/types.py:6-9`

```
Signal
├── BUY            = "BUY"            (existing)
├── SELL           = "SELL"           (existing)
├── HOLD           = "HOLD"           (existing)
├── SELL_SHORT     = "SELL_SHORT"     ← NEW
└── BUY_TO_COVER   = "BUY_TO_COVER"   ← NEW
```

**Mapping**: `TradeSignal(signal=Signal.SELL_SHORT)` → RiskManager → `Order(side=OrderSide.SELL_SHORT)`.

---

### E5: DecisionAction (extended)
`src/agent/journal.py:24`

```
DecisionAction = Literal[
    "BUY",            # existing
    "SELL",           # existing
    "HOLD",           # existing
    "ADJUST_STOP",    # existing
    "SELL_SHORT",     # NEW — open a short position
    "BUY_TO_COVER",   # NEW — close a short position
]
```

**New action semantics**:
- `SELL_SHORT` + `stop` → short entry with mandatory stop-loss
- `SELL_SHORT` without `stop` → executor skips (FR-4.1: mandatory stop)
- `BUY_TO_COVER` + optional `cover_pct` → partial/full short cover

---

### E6: Order (modified)
`src/core/models.py:32-81`

Existing validator extended for short bracket semantics:

```
Order
├── ...existing fields...
├── side: OrderSide  (now includes SELL_SHORT, BUY_TO_COVER)
│
└── _check_bracket_legs()  ← MODIFIED
    ├── BRACKET + BUY  → take_profit > limit_price, stop_loss < limit_price  (existing)
    ├── BRACKET + SELL_SHORT → take_profit < limit_price, stop_loss > limit_price  (NEW)
    └── OCO + BUY_TO_COVER  → take_profit < limit_price, stop_loss > limit_price  (NEW — cover protection)
```

**Short Bracket Invariant** (PBT-03):
- `side == SELL_SHORT and order_class == BRACKET`
  → `stop_loss_price > limit_price and take_profit_price < limit_price`

---

### E7: PortfolioState (unchanged structure, semantics change)
`src/core/models.py:124-138`

No structural change. `positions: dict[str, Position]` still keyed by symbol only. But now a Position can have `side=LONG` or `side=SHORT`. The executor's auto-flip logic (FR-3) ensures only one direction exists per symbol at any time.

---

### Entity Relationships

```
┌──────────────┐     contains      ┌──────────────┐
│PortfolioState│──────────────────▶│   Position   │
│              │  dict[symbol,Pos] │  +side: enum  │
└──────────────┘                   └──────┬───────┘
                                          │ becomes
                                          ▼
┌──────────────┐     references    ┌──────────────┐
│ TradeSignal  │──────────────────▶│   Signal     │
│  +signal     │                   │ +SELL_SHORT  │
└──────┬───────┘                   │ +BUY_TO_COVER│
       │                           └──────────────┘
       │ evaluated by
       ▼
┌──────────────┐     produces      ┌──────────────┐
│ RiskManager  │──────────────────▶│    Order     │
│ +short logic │                   │ +side ext.   │
└──────────────┘                   └──────┬───────┘
                                          │ submitted to
                                          ▼
                                   ┌──────────────┐
                                   │  BaseBroker  │
                                   │ submit_order │
                                   └──────────────┘
```

## Testable Properties (PBT-01)

| Entity | Property | Category | PBT Rule |
|--------|----------|----------|----------|
| Position.update_price | SHORT: price↓ → uPNL > 0, price↑ → uPNL < 0 | Invariant | PBT-03 |
| Order._check_bracket_legs | SELL_SHORT bracket: stop > limit, target < limit | Invariant | PBT-03 |
| Order JSON round-trip | Order(SHORT) → json → Order = equal | Round-trip | PBT-02 |
| Decision JSON round-trip | Decision(SELL_SHORT) → json → Decision = equal | Round-trip | PBT-02 |

# Unit A: Trading Core — NFR Design Patterns

> **Track**: F54 / Unit A
> **Date**: 2026-06-04

## P1: Fail-Closed Validation Chain (SECURITY-15)

Short order validation is a **chain**: each stage rejects on first failure.

```
Signal → RiskManager.evaluate_signal()
  ├── [1] Circuit breaker: _new_shorts_halted? → reject
  ├── [2] Pool: position_count ≥ max? → reject
  ├── [3] Existing: same symbol same side? → skip
  ├── [4] Stop source: explicit stop or ATR? → reject if neither (MANDATORY)
  ├── [5] Bracket geometry: valid stop/target direction? → reject
  ├── [6] Position size: shares > 0? → reject
  └── [7] → Order
```

No fallback to "simple market short without stop" — the chain stops at [4].

## P2: Defense-in-Depth (NFR-1.2)

Three layers, each independently verifiable:

```
Layer 1: Agent/Strategy     →  Analysis tools warn (short interest, borrow cost)
Layer 2: RiskManager        →  Mandatory stop, direction validation, sizing
Layer 3: Broker (Alpaca)    →  API-level short eligibility, margin check
```

Layer 2 is the structural gate; Layers 1 and 3 are complementary. No single layer failure should allow an unsafe short.

## P3: Direction-Aware Computation

All price-relative computations accept a `PositionSide` parameter:

```python
def _stop_loss_triggered(entry, current, side, pct) -> bool:
    if side == PositionSide.LONG:
        return (entry - current) / entry >= pct
    return (current - entry) / entry >= pct
```

No `if side == SHORT` scattered through call sites — the direction switch is localized in the risk module.

## P4: Auto-Flip Transaction Boundary

Auto-flip (BR-6) is a **two-phase transaction** within `execute_decision()`:

```python
# Phase 1: Close existing (blocking, must succeed)
close_filled = broker.submit_order(close_order)
if close_filled.qty < position.qty:
    return ExecutionOutcome(..., "error", "partial close, flip aborted")

# Phase 2: Enter new (fresh portfolio snapshot)
portfolio = broker.get_portfolio_state()
new_order = risk_manager.evaluate_signal(new_signal, price, portfolio)
new_filled = broker.submit_order(new_order)
```

Each phase logs separately. The flip is NOT atomic — if Phase 2 fails after Phase 1 succeeds, the position is simply closed (not left in an inconsistent state).

## P5: PBT Integration Points

Tests in `tests/test_short_risk.py` (new file, Hypothesis):

```python
from hypothesis import given, strategies as st

@given(price=st.floats(1, 1000), entry=st.floats(1, 1000))
def test_short_pnl_sign(price, entry):
    """Price below entry → positive P&L for shorts."""
    pos = Position(symbol="X", qty=10, avg_entry_price=entry, side=PositionSide.SHORT)
    pos.update_price(price)
    if price < entry:
        assert pos.unrealized_pnl >= 0
    elif price > entry:
        assert pos.unrealized_pnl <= 0

@given(entry=st.floats(1, 500), stop=st.floats(1, 1000))
def test_short_stop_above_entry(entry, stop):
    """Resolved short stop must be > entry or None."""
    rm = RiskManager(use_bracket_orders=True)
    result = rm._resolve_short_stop(entry, stop, None)
    assert result is None or result > entry
```

## P6: Config Fallback Chain

Short parameters follow a fallback chain: `short_*` → base parameter:

```python
def _short_stop_loss_pct(self) -> float:
    return self._short_stop_loss_pct_override or self.stop_loss_pct
```

No duplication — a single `or` pattern in each getter.

## NFR Compliance Summary

| Rule | Status | Evidence |
|------|--------|----------|
| SECURITY-03 | ✅ Compliant | loguru structured logging, no secrets in order logs |
| SECURITY-11 | ✅ Compliant | Short risk logic isolated in RiskManager |
| SECURITY-15 | ✅ Compliant | P1 fail-closed chain, P4 transaction boundary |
| PBT-02 | ✅ Compliant | Order/Decision JSON round-trip tests planned |
| PBT-03 | ✅ Compliant | P&L sign, stop ceiling, bracket geometry invariants |
| PBT-07/08/09 | ✅ Compliant | Hypothesis strategies + shrinker + framework |

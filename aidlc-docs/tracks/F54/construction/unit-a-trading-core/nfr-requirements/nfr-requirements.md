# Unit A: Trading Core — NFR Requirements

> **Track**: F54 / Unit A
> **Depth**: Minimal (NFRs already defined in requirements; no new runtime deps)
> **Date**: 2026-06-04

## Assessment

**0 new runtime dependencies.** alpaca-py natively supports `sell_short`/`buy_to_cover` sides on all order types including bracket/OCO. No new Python packages needed.

## Security (SECURITY-03, SECURITY-11, SECURITY-15)

| Rule | Applicable? | How |
|------|------------|-----|
| SECURITY-03 | ✅ Yes | Short order logs exclude API keys/tokens; loguru structured logging unchanged |
| SECURITY-11 | ✅ Yes | Risk/short logic isolated in `RiskManager`; no other module computes stop/target for shorts |
| SECURITY-15 | ✅ Yes | All short validation fail-closed: missing stop→reject, invalid geometry→reject, price fetch fail→reject |

## Property-Based Testing (Partial mode)

| Rule | Applicable? | Targets |
|------|------------|---------|
| PBT-02 | ✅ Round-trip | `Order`/`Decision` JSON serialize→deserialize with SELL_SHORT/BUY_TO_COVER |
| PBT-03 | ✅ Invariant | `Position.update_price()` short P&L sign; `_resolve_short_stop` ceiling invariant; bracket geometry |
| PBT-07 | ✅ Generators | Hypothesis strategies for valid Order/Decision with short sides |
| PBT-08 | ✅ Shrinking | Default Hypothesis shrinker for counterexamples |
| PBT-09 | ✅ Framework | Hypothesis (already in dev deps) |

PBT-01/04/05/06: Advisory only (Partial mode).

## Performance

- No new network calls (alpaca-py already imported)
- `Position.update_price()`: one extra `if side == SHORT` branch — negligible
- `RiskManager.evaluate_signal()`: two new branches (SELL_SHORT, BUY_TO_COVER) — O(1)

## Reliability

- Auto-flip (BR-6): close+enter sequence, close failure→abort
- SimulatedBroker must track short positions for paper testing

## Tech Stack (unchanged)

- Python 3.11+, pydantic, loguru, alpaca-py, pandas, APScheduler
- Dev: pytest, Hypothesis

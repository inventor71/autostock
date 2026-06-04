# F60 — Build & Test Summary

> **Track**: F60 — Easy-to-borrow 숏 게이트
> **Date**: 2026-06-04
> **Branch**: feat/F60 (off feat/F59 @ 41183fd)

## What changed
Shorts are now limited to **easy-to-borrow** names via a live broker pre-gate.

| Layer | Change |
|-------|--------|
| `BaseBroker.is_shortable(symbol)` | New capability; default `True` (simulated/backtest have no borrow concept) |
| `AlpacaBroker.is_shortable` | `tradable AND shortable AND easy_to_borrow` from `get_asset`; 30-min cache; **fail-closed False** on any error |
| `DecisionExecutor.execute_decision` | SELL_SHORT gated BEFORE auto-flip → a non-ETB short never closes an existing long; `skipped_not_shortable` (terminal) |
| `commands._submit_gated` | SELL_SHORT ETB gate shared by `/short` + `place_order`; not force-overridable |
| `prompts._SHORT_GUIDANCE` | Tells the agent shorts are ETB-only (don't waste a decision) |

## Results
- **Python full suite: 801 passed** (+7 new ETB tests). 0 regressions, 0 new deps.
- buy / place_order / human-order-gate paths unaffected: 77 passed.
- **Live read-only verify (real Alpaca paper)**: `is_shortable` → AAPL/TSLA/SPY = True
  (easy-to-borrow large caps). Fail-closed False path covered by `_NoBorrow` unit tests.

## Test coverage (`tests/test_short_etb_gate.py`)
- base default permissive; agent short rejected/allowed by ETB
- ETB gate blocks the long→short flip before closing the long
- `skipped_not_shortable` is terminal (cursor advances, not retried)
- human `/short` rejected/allowed by ETB

## Security (Baseline)
- SECURITY-15 fail-closed: ETB unconfirmable → not shortable; gate not force-overridable. ✓
- SECURITY-03: no secrets in logs. ✓

## Why this matters (user's concern)
"빌려서 판다" 리스크의 실체 = 차입비 + 리콜/buy-in(강제청산). 둘 다 hard-to-borrow에서 터짐.
ETB 한정으로 유니버스를 유동성 큰 종목에 묶어 두 리스크를 구조적으로 낮춤. 만기 없는 무한손실
가능성은 F54의 필수 하드스톱이 별도로 방어.

## Verdict: ✅ PASS — ready to merge (after F59)

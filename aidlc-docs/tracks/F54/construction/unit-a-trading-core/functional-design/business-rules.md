# Unit A: Trading Core — Business Rules

> **Track**: F54 / Unit A
> **Phase**: Functional Design
> **Date**: 2026-06-04

## BR-1: Mandatory Short Stop-Loss (FR-4.1)

**Rule**: 모든 숏 진입은 반드시 `stop_loss_price`를 가져야 한다. 손절가가 없으면 주문이 거부된다.

| Condition | Result |
|-----------|--------|
| SELL_SHORT + stop_loss present + valid direction | Accept |
| SELL_SHORT + stop_loss missing | Reject — `NO_STOP` |
| SELL_SHORT + ATR available → auto-stop resolved | Accept (auto-protect) |
| SELL_SHORT + ATR unavailable + no explicit stop | Reject — `NO_STOP` |

**Rationale**: Long max loss = 100%. Short max loss = ∞. Structural protection required.

---

## BR-2: Short Bracket Geometry (FR-1.5, FR-4.1.2)

**Rule**: 숏 브라켓 오더의 손절/익절은 롱의 반대 방향이어야 한다.

| Check | Long (BUY) | Short (SELL_SHORT) |
|-------|-----------|-------------------|
| Stop vs Entry | `stop_loss < entry` | `stop_loss > entry` |
| Target vs Entry | `take_profit > entry` | `take_profit < entry` |
| Target floor | N/A (always above entry) | `take_profit > 0` (can't go below zero) |

**Violation → `PRICE_SANITY` reject**. Price sanity checks are NOT overridable by `force`.

---

## BR-3: Short Stop Resolution (FR-4.1.3)

**Rule**: `_resolve_short_stop(entry, stop, atr)`:

```
1. Explicit stop > entry → use it
2. ATR available → entry + atr_stop_multiple * atr
3. Neither → None → REJECT (mandatory stop)
4. Cap: ceiling = entry * (1 + max_stop_distance_pct)
   └── if resolved > ceiling → use ceiling
5. Guard: resolved <= entry → None (invalid)
```

---

## BR-4: Short Stop Ratchet (FR-4.3)

**Rule**: 숏 손절은 아래로만 조정(타이트하게)된다.

| Side | Ratchet direction | Function |
|------|------------------|----------|
| LONG | Tighten = raise stop | `max(current, proposed)` |
| SHORT | Tighten = lower stop | `min(current, proposed)` |

`allow_widen=True` → ratchet bypass, direct proposed value used.

---

## BR-5: Short Cover Quantity (FR-2.3)

**Rule**: 숏 커버 수량은 보유 숏 포지션의 `qty`를 초과할 수 없다.

```
qty = min(round(position.qty * cover_pct, 9), position.qty)
if qty <= 0 → skip (ZERO_QTY)
```

---

## BR-6: Auto-Flip All-or-Nothing (FR-3)

**Rule**: 방향 전환은 전체 청산 성공 후에만 반대 진입을 시도한다.

| Step | Success | Failure |
|------|---------|---------|
| Close existing position | Proceed to new entry | Abort flip, return error |
| Enter new position | Log both outcomes | Log close success + entry failure |

Partial fills on close: if `filled.qty < position.qty`, abort flip (remaining position exists, state ambiguous).

---

## BR-7: Dual Circuit Breaker (FR-5)

**Rule**: 롱과 숏은 독립적인 서킷 브레이커를 가진다.

| Breaker | Trigger | Default |
|---------|---------|---------|
| `_new_buys_halted` | SPY day-change ≤ `market_halt_threshold_pct` | -3% |
| `_new_shorts_halted` | SPY day-change ≥ `short_market_halt_threshold_pct` | +3% |

Individual stock breaker:
| Condition | Action |
|-----------|--------|
| Stock day-change ≥ 10% | Reject new shorts on this symbol |

`force=True` overrides circuit breakers for human orders.

---

## BR-8: Position Pool Constraint

**Rule**: `portfolio.position_count >= max_open_positions` → 신규 진입 거부 (롱/숏 모두).

Same as existing, direction-agnostic. Overridable by `force=True`.

---

## BR-9: Same-Symbol Same-Direction Guard

**Rule**: 이미 보유 중인 심볼에 대해 같은 방향으로 추가 진입할 수 없다.

| Existing | New Signal | Result |
|----------|-----------|--------|
| LONG | BUY | Skip ("already holding") |
| SHORT | SELL_SHORT | Skip ("already holding short") |
| LONG | SELL_SHORT | Auto-flip (BR-6) |
| SHORT | BUY | Auto-flip (BR-6) |

---

## BR-10: Protection Placement Direction (FR-8.3)

**Rule**: `_place_protection()`은 포지션 방향에 따라 적절한 주문 측면을 선택한다.

| Position Side | Protective Order Side | Stop Position |
|--------------|----------------------|---------------|
| LONG | SELL | Below current price |
| SHORT | BUY_TO_COVER | Above current price |

---

## BR-11: Polled Exit Direction (FR-4.4)

**Rule**: 폴드 백업 손절/익절 체크는 포지션 방향에 따라 손익 계산을 반전한다.

| Check | LONG formula | SHORT formula |
|-------|-------------|---------------|
| Stop loss | `(entry - current) / entry ≥ pct` | `(current - entry) / entry ≥ pct` |
| Take profit | `(current - entry) / entry ≥ pct` | `(entry - current) / entry ≥ pct` |

---

## BR-12: Fail-Closed Default (SECURITY-15, NFR-1.1)

**Rule**: 모든 숏 관련 검증은 실패 시 기본적으로 거부한다.

| Scenario | Default |
|----------|---------|
| Unknown OrderSide | Reject |
| Missing stop on short | Reject |
| Invalid bracket geometry | Reject |
| Price fetch failure | Reject (can't validate) |
| Broker error on submit | Raise, don't silently skip |

---

## BR-13: Short P&L Sign Convention (FR-10.2)

**Rule**: `Position.update_price()`의 P&L 계산:

```
LONG:  unrealized_pnl = market_value - cost_basis
       (price↑ → pnl↑, 기존)
SHORT: unrealized_pnl = cost_basis - market_value
       (price↓ → pnl↑, 신규)
```

This ensures `unrealized_pnl > 0` always means profit regardless of direction.

---

## BR-14: Order Model Validation (FR-10.3)

**Rule**: `Order._check_bracket_legs()` 확장:

```
BRACKET/OCO + side ∈ {BUY, SELL}:
    take_profit > limit_price, stop_loss < limit_price  (existing)

BRACKET/OCO + side ∈ {SELL_SHORT, BUY_TO_COVER}:
    take_profit < limit_price, stop_loss > limit_price  (NEW)
```

## Configurable Parameters (settings.yaml)

```yaml
risk:
  # Existing (unchanged)
  stop_loss_pct: 0.05
  take_profit_pct: 0.15
  max_position_pct: 0.10
  max_portfolio_risk: 0.02
  max_open_positions: 10
  max_stop_distance_pct: 0.12
  atr_stop_multiple: 3.0
  market_halt_threshold_pct: -0.03
  default_risk_reward: 2.5

  # NEW — short-specific (all optional, fallback to long values)
  short_market_halt_threshold_pct: 0.03    # +3% SPY → halt shorts
  short_stop_loss_pct: null                 # null = use stop_loss_pct
  short_take_profit_pct: null               # null = use take_profit_pct
  short_max_position_pct: null              # null = use max_position_pct
  short_max_portfolio_risk: null            # null = use max_portfolio_risk
  short_max_stop_distance_pct: null         # null = use max_stop_distance_pct
  individual_stock_halt_pct: 0.10           # 10% day-up → reject short
```

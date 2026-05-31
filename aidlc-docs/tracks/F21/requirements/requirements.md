# F21 Requirements — structured MCP order arg robustness (fail-fast + omit-optional guidance)

> Track: F21 | Type: Bug Fix (F9 follow-up) | Depth: Minimal | 2026-05-31
> Scope: all 3 structured MCP tools (`place_stock_order`, `close_position`, `close_all_positions`)
> Architecture: 3-layer validation (L1 zod `.refine()` → L2 `handleStructured` → L3 daemon defense-in-depth)

## Intent Analysis

- **User request**: 약한 콘솔 모델이 optional 필드에 placeholder(`0.01`)를 채우고, `qty`+`notional` 동시 설정한 malformed 주문이 장 마감 시 "deferred"로 보고되었으나 개장 시 거부됨. 동일 패턴이 `close_position`, `close_all_positions`에도 존재. Alpaca MCP처럼 **동기 검증 → agent retry 가능** 구조로 개선.
- **Request type**: Bug Fix + Enhancement
- **Scope**: Multiple Components — (1) TypeScript `mcp-server.ts` zod schema (L1 `.refine()`), (2) TypeScript `steer-handler.ts` (L2 degenerate check), (3) Python `commands.py` (L3 simplified), (4) wording
- **Complexity**: Moderate — cross-language, 3개 tool, validation 로직 재배치

## Root Cause & Architectural Gap

**직접 원인**: `commands.py`의 off-hours verb들이 queue 전에 structural validation을 하지 않음.

**구조적 원인**: 현재 MCP tool은 fire-and-forget — `handleStructured`가 file-drop에 쓰고 즉시 `"OK <id>"` 반환. 실제 검증 결과는 daemon이 비동기로 events.jsonl에 기록. **Agent는 tool response에서 에러를 보지 못해 retry 불가능.** Alpaca MCP는 모든 검증을 동기적으로 하고 `{"error": ...}`를 tool response에 반환 — agent가 즉시 보고 수정 가능.

**해결**: 3-layer validation으로 structural 검증을 MCP 서버(L1 zod)로 올리고, daemon(L3)은 가격 기반 검증만 담당.

## 3-Layer Validation Architecture

```
Agent calls place_stock_order({symbol: "AAPL", qty: 1, notional: 0.01, ...})
  │
  ▼
┌─ L1: Zod schema (.refine()) ──────────────────────────────────┐
│  type/enum/required + cross-field rules                        │
│  → 실패: MCP SDK가 agent에게 {"error": "..."} 즉시 반환        │
│  → 통과: args가 L2로 전달                                      │
└────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─ L2: handleStructured (degenerate check) ─────────────────────┐
│  domain judgment: 0.01 같은 placeholder 감지                   │
│  → 실패: "rejected: <reason>" 반환 (agent가 즉시 봄)           │
│  → 통과: file-drop에 write → daemon으로                         │
└────────────────────────────────────────────────────────────────┘
  │ (file-drop: commands.jsonl)
  ▼
┌─ L3: Daemon gate (commands.py) ───────────────────────────────┐
│  pydantic extra="forbid" + 가격 기반 사이즈 계산 + price sanity │
│  → 실패: events.jsonl에 reject 기록                             │
│  → 통과: queue_offhours 또는 즉시 submit                        │
└────────────────────────────────────────────────────────────────┘
```

## Policy Decisions (confirmed 2026-05-31)

| # | 질문 | 결정 |
|---|------|------|
| P1 | Degenerate optional 값 처리 | **Hard-reject + 이유** (sanitize-to-None 아님). L2에서 감지하여 동기 반환 |
| P2 | Pre-queue 검증 범위 | **구조 검증은 L1/L2로 이동**, L3는 가격 기반만. Alpaca MCP 패턴 따름 |
| P3 | qty+notional 둘 다 설정 시 | **Hard-reject 유지** — L1 zod `.refine()`에서 동기 반환 |
| P4 | L3에서 중복 검증 로직 | **삭제**. L1에서 이미 걸러졌으므로 L3는 `extra="forbid"` pydantic validation만 defense-in-depth로 유지. `_order_from_place_args`에서 FR-7 로직 제거, 가격 기반 계산만 남김 |

## Functional Requirements

### FR-1: `place_stock_order` — L1 zod `.refine()` (TypeScript — `mcp-server.ts`)

**현재 zod schema**:
```typescript
inputSchema: {
  symbol: z.string(),
  side: z.enum(["buy", "sell"]),
  qty: z.number().positive().optional(),
  notional: z.number().positive().optional(),
  // ... plain per-field validation only, no cross-field rules
}
```

**변경**: `.refine()` / `.superRefine()` chain 추가하여 cross-field validation을 zod 자체에서 수행:

**FR-1.1** — `qty`와 `notional` mutual exclusivity:
```typescript
.refine(d => !(d.qty != null && d.notional != null), {
  message: "specify either qty or notional, not both",
  path: ["qty"],
})
```

**FR-1.2** — `qty` 또는 `notional` 중 하나는 필수:
```typescript
.refine(d => d.qty != null || d.notional != null, {
  message: "qty or notional required",
})
```

**FR-1.3** — `notional`은 market + day 전용 (FR-7):
```typescript
.refine(d => d.notional == null || (d.order_type === "market" && d.time_in_force === "day"), {
  message: "notional is only allowed for market + day orders",
  path: ["notional"],
})
```

**FR-1.4** — `trail_price`/`trail_percent`는 `trailing_stop` 전용:
```typescript
.refine(d => d.order_class === "trailing_stop" || (d.trail_price == null && d.trail_percent == null), {
  message: "trail_price/trail_percent only valid with order_class=trailing_stop",
  path: ["trail_price"],
})
```

**FR-1.5** — `qty`는 정수 (Alpaca는 fractional bracket leg 거부):
```typescript
.refine(d => d.qty == null || Number.isInteger(d.qty), {
  message: "qty must be an integer (fractional shares not supported for bracket legs)",
  path: ["qty"],
})
```

**FR-1.6** — Zod description tightening (기존 FR-4 계승):
- `notional`: `"$ amount; market+day only. Omit if using qty. Do NOT pass 0 or placeholder"`
- `qty`: `"integer share count. Omit if using notional"`
- `trail_price`, `trail_percent`: `"only for trailing_stop order_type; omit otherwise"`
- `take_profit`, `stop_loss`, `limit_price`, `stop_price`: 기존 `.positive()` 유지 + `"omit if unused; do NOT pass 0 or placeholder"`
- Tool description: `"Omit optional fields entirely if unused. Never pass 0, 0.01, or placeholder values. Errors are returned synchronously — read the error and retry with corrected args."`

### FR-2: `place_stock_order` — L2 degenerate check (TypeScript — `steer-handler.ts`)

**FR-2.1** — `handleStructured`에서 file-drop write 전에 degenerate 값 감지:
- L1 zod `.positive()`는 `> 0`만 체크 — `0.01` 같은 값은 통과
- L2에서 `take_profit`, `stop_loss`, `trail_price`, `trail_percent`, `limit_price`, `stop_price`가 `> 0 && ≤ 0.01` 이면 → `"rejected: take_profit 0.01 looks like a placeholder; omit if unused"` 반환
- `notional ≤ 0.01` → 동일 처리

**FR-2.2** — L2 거부는 file-drop에 쓰지 않고 즉시 문자열로 반환 → agent가 tool response에서 즉시 확인

### FR-3: `place_stock_order` — L3 daemon simplified (Python — `commands.py`)

**FR-3.1** — `_v_place_order` 실행 순서 변경:
```
현재:  parse → queue_offhours → _order_from_place_args (FR-7 포함) → submit
변경:  parse → queue_offhours → _order_from_place_args (가격만) → submit
```
L1/L2에서 structural 검증을 이미 통과했으므로, L3에서는 `PlaceOrderArgs.model_validate(extra="forbid")` + 가격 기반 계산만 수행.

**FR-3.2** — `_order_from_place_args` 단순화:
- **제거**: FR-7 exclusivity 체크 (→ L1 FR-1.1), notional market+day 체크 (→ L1 FR-1.3), trail/class 체크 (→ L1 FR-1.4)
- **유지**: notional→qty 변환 (live price 필요), qty floor, qty≤0 체크
- **유지**: `OrderClass.SIMPLE + take_profit/stop_loss → BRACKET` auto-upgrade
- **유지**: `Order()` 생성 (모든 필드 그대로 전달, RiskManager에서 최종 검증)

**FR-3.3** — Defense-in-depth: `extra="forbid"` + pydantic type validation은 그대로 유지. TS 쪽에서 typo나 누락된 필드가 있으면 daemon에서 최종 catch.

### FR-4: `close_position` — L1 zod `.refine()` (TypeScript — `mcp-server.ts`)

**FR-4.1** — `symbol` required + non-empty:
```typescript
symbol: z.string().min(1).describe("ticker symbol (e.g. AAPL)")
```

**FR-4.2** — `qty`와 `percentage` mutual exclusivity:
```typescript
.refine(d => !(d.qty != null && d.percentage != null), {
  message: "specify either qty or percentage, not both",
})
```

**FR-4.3** — `percentage` range:
```typescript
percentage: z.number().gt(0).lte(100).optional()
```
(현재는 `.positive().max(100)` → `.gt(0)`로 변경하여 0 방지)

**FR-4.4** — Description tightening:
- `qty`: `"share count to close. Omit if using percentage"`
- `percentage`: `"percentage of position to close (1-100). Omit if using qty"`
- Tool description에 Alpaca MCP 패턴 가이던스 추가

### FR-5: `close_position` — L3 daemon simplified (Python — `commands.py`)

**FR-5.1** — `_v_close_position`에서 queue 전 arg 검증 추가:
- 현재는 `cmd.args["symbol"]` 바로 접근 → symbol 없으면 KeyError (drain crash 위험)
- `symbol`이 없거나 빈 문자열 → 즉시 reject (L1에서 걸러지지만 defense-in-depth)
- 검증 통과 후 `queue_offhours` 진입

**FR-5.2** — L3 유지: `get_position(sym) is None` → "no position" reject (broker state 필요, L1 불가)

### FR-6: `close_all_positions` — L3 minimal (Python — `commands.py`)

**FR-6.1** — `_v_close_all`에서 queue 전 최소 검증:
- `cancel_orders`가 boolean/undefined인지 확인 (L1 zod가 보장하지만 defense-in-depth)
- 검증 후 `queue_offhours` 진입

### FR-7: Wording (Python — `commands.py`)

**FR-7.1** — L1/L2에서 이미 structural 검증을 통과했으므로, queue 메시지를 정직하게:
- `place_order`: "market closed; queued for next open (size/price validated at open)"
- `close_position`: "market closed; queued for next open (position checked at open)"
- `close_all`: "market closed; queued for next open"

**FR-7.2** — 개장 드레인 시 reject 기록에 off-hours context 포함

## Validation Logic Relocation Summary

| 검증 | 현위치 | → 이동 | 이유 |
|------|--------|--------|------|
| qty/notional exclusivity | L3 `_order_from_place_args` | **L1 zod `.refine()`** | 동기 반환, agent retry 가능 |
| qty or notional required | L3 `_order_from_place_args` | **L1 zod `.refine()`** | 동일 |
| notional market+day only | L3 `_order_from_place_args` | **L1 zod `.refine()`** | 동일 |
| trail/class validity | L3 `_order_from_place_args` | **L1 zod `.refine()`** | 동일 |
| qty integer check | (신규) | **L1 zod `.refine()`** | fractional bracket leg 방지 |
| degenerate 값 (≤0.01) | (신규) | **L2 `handleStructured`** | Positive 통과한 placeholder 감지 |
| symbol required (close_position) | (없음→KeyError) | **L1 zod `.min(1)`** + **L3 defense** | drain crash 방지 |
| qty/percentage exclusivity | (없음) | **L1 zod `.refine()`** | operator confusion 방지 |
| notional→qty 변환 | L3 `_order_from_place_args` | L3 유지 | live price 필요 |
| qty floor, 0체크 | L3 `_order_from_place_args` | L3 유지 | live price + qty 필요 |
| take_profit/stop_loss sanity | L3 `_order_from_place_args` | L3 유지 | live price + entry 필요 |
| position 존재 여부 | L3 `_v_close_position` | L3 유지 | broker state 필요 |

## Non-Functional Requirements

- **NFR-1 (No new deps)**: 0 new runtime dependencies. zod `.refine()`/`.superRefine()`는 이미 dependency에 포함된 zod의 built-in 기능.
- **NFR-2 (Fail-closed, SECURITY-15)**: L1/L2/L3 3중 defense-in-depth. L1 zod가 primary gate, L2 degenerate가 secondary, L3 pydantic이 tertiary.
- **NFR-3 (Cross-language contract)**: zod schema 변경 시 `contract.json`, `schema.ts`의 `COMMAND_ARGS`와 sync 유지.
- **NFR-4 (Backward compat)**: 기존 정상 호출은 변경 후에도 동일하게 동작. L1 `.refine()` 추가로 인해 이전에는 통과하던 malformed 호출이 reject될 수 있으나, 이는 의도된 동작 (원래 daemon에서 reject되던 것들).
- **NFR-5 (Alpaca MCP pattern)**: `{"error": "..."}` 형식으로 동기 반환 → agent가 즉시 retry 가능. Alpaca MCP의 `_error` 헬퍼 패턴 참고.

## Out of Scope

- `cancel_order`, `replace_order` 등 queue 패턴 없는 tool
- Deterministic shorthand (`/sell`, `/flatten`, `/flatten all`, `/stop`, `/kill`)
- `close_position`에 partial close(qty/percentage) 기능 추가
- MCP tool이 daemon 응답을 polling해서 최종 outcome까지 동기 반환 (L3 결과는 여전히 비동기 — structural validation만 동기화)
- Zod schema에 `.refine()`으로 가격 sanity 검증 (live price 필요 → L3에서만 가능)

## Key Summary

1. **L1 zod `.refine()`**: structural cross-field 검증을 MCP 서버로 올려 동기 반환 → agent가 즉시 에러를 보고 retry 가능 (Alpaca MCP 패턴)
2. **L2 degenerate check**: `0.01` 같은 placeholder를 domain judgment로 감지 → 동기 거부
3. **L3 daemon simplified**: `_order_from_place_args`는 가격 기반 계산만 담당, FR-7 로직 제거. Defense-in-depth로 `extra="forbid"` pydantic 유지
4. **3개 tool 모두 적용**: `place_stock_order`, `close_position`, `close_all_positions`
5. **Wording 정직화**: "deferred ≠ validated-accepted"

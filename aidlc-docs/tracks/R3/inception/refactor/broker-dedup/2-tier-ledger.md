# Tier Ledger — broker-dedup (R3)

범위: `src/execution/brokers/{alpaca_broker,broker_api_broker}.py` → new `_alpaca_shaped.py` base
작성일: 2026-06-06

Target structure: a `AlpacaShapedBroker(BaseBroker)` template-method base holding the shared
algorithm; `AlpacaBroker` and `BrokerApiBroker` become thin subclasses providing only client-specific
hooks + request-class sets. See `3-redesign.md` (written after the T3 gate).

## T1 — 동작 보존 (자율 진행)
| # | 변경 항목 | 보존되는 동작 | 보존 검증 방식 | 근거 |
|---|-----------|---------------|----------------|------|
| 1 | Move `_ALPACA_TO_ORDER_TYPE`, `_TERMINAL_STATUSES` to base module | identical constants | existing tests exercise both paths | byte-identical |
| 2 | Move `_position_side`, `_to_open_order` (static) to base | identical mapping | `test_broker_api_broker.py` (positions/open-orders) + new Alpaca tests | identical code |
| 3 | `_poll_for_fill` → base, calls abstract `_get_order(id)` | same poll loop/timeout | submit/close tests both brokers | same loop |
| 4 | `submit_order`/`close_position`/`get_order_status`/`cancel_order` → base template + client hooks | same returns/errors | broker_api tests (strong) + **new Alpaca tests** | same algorithm |
| 5 | `get_position`/`get_all_positions`/`get_portfolio_state` → base + `_open_position`/`_all_positions`/`_account` hooks (D7) | same normalization, qty>0, None/raise semantics | broker_api tests + new Alpaca tests | same algorithm |
| 6 | `is_market_open`/`is_shortable` → base, client attr via hook | same retries, fail-closed, TTL cache | broker_api tests + new Alpaca tests | identical except client attr |
| 7 | `get_open_orders` → base template; **status filter + terminal-skip as subclass-overridable** (D4) | each broker keeps its own filter behavior | broker_api leg-flatten test + new Alpaca OPEN-filter test | filter stays per-subclass |
| 8 | `get_fills` → base template; `_parse_fill(activity)` + `_activities(since)` hooks (D5) | each broker's parser/feed preserved | broker_api fills tests + new Alpaca dict-parse test | mapper stays per-subclass |
| 9 | `get_latest_prices` → base template; `_make_data_client()` hook (D6) | each broker's data-client construction preserved | broker_api latest-prices test + new Alpaca test | construction stays per-subclass |
| 10 | `record_trade_ledger` → base template; `_ledger_client()` hook (D8) | both delegate to `record_trades` unchanged | broker_api ledger-shim test + Alpaca ledger-port test | same delegation |
| 11 | `_build_request` bracket/OCO/market/limit/stop/stop-limit branches → base; request-class set as subclass attrs (D9) | same request objects per type | new Alpaca `_build_request` tests + broker_api submit tests | structurally identical |

**모든 T1 항목은 단계 1 특성화 테스트로 보호되어야 함.** broker_api 쪽은 기존 테스트로 충분.
Alpaca 쪽은 **공백** → 단계 1에서 특성화 테스트 추가 후 진행 (T1 게이트 준수).

## T2 — 안전한 확장 (자율 진행 + 사후 보고)
| # | 추가 항목 | 기존 동작 영향 | 보존 검증 방식 |
|---|-----------|----------------|----------------|
| (none yet — pending T3 gate; D3 may land here if user chooses "preserve, no change") | | | |

## T3 — 의도 변경 / 기능 cut (🛑 승인 필요)
> These collapse a real behavior difference onto one shared implementation. Each needs a decision:
> **(a) preserve** both behaviors via a subclass hook (keeps T1, more code), or **(b) unify** onto
> one behavior (less code, but changes one broker — the actual T3).

| # | 변경 내용 | 이유(복잡도 비용) | 얻는 것 | 잃는 것 | 영향 범위 | 사용자 결정 |
|---|-----------|-------------------|---------|---------|-----------|-------------|
| T3-1 | **Side mapping**: adopt shared `_alpaca_side` for both → `BrokerApiBroker` would map `BUY_TO_COVER→BUY`, `SELL_SHORT→SELL` and raise on unknown (today it does `BUY if ==BUY else SELL`, so BUY_TO_COVER wrongly→SELL) | Keeping broker_api's simplistic mapping means the base can't own `submit_order`'s side step — needs a per-subclass side hook just to preserve a likely-bug | Fixes a latent short-cover bug; one shared side mapper | broker_api's current (arguably wrong) short-side behavior on the sandbox farm | broker_api short/cover orders only (sandbox account farm; shorting there likely unexercised) | **유지 (preserve)** → deferred to **R7** |
| T3-2 | **TIF**: adopt shared fail-closed TIF map for both → `BrokerApiBroker` would **reject** ioc/fok/unsupported (today it silently downgrades non-gtc to DAY) | Preserving broker_api's silent-downgrade needs a separate TIF resolver in the base | One fail-closed TIF policy (no silent downgrade — matches F9 intent) | broker_api's lenient "downgrade to DAY" behavior | broker_api orders with ioc/fok/opg/cls TIF | **유지 (preserve)** → deferred to **R7** |
| T3-3 | **`_build_request` extras/trailing**: base builds with `_extras` (extended_hours/client_order_id) + TRAILING_STOP for both → `BrokerApiBroker` gains these paths | broker_api's `alpaca.broker.requests` classes may not accept extended_hours/client_order_id/trailing; supporting needs verification or a no-op `_extras` override | Single `_build_request`; broker_api gains extended-hours/trailing if SDK supports | risk that broker.requests rejects these kwargs (needs SDK check) | broker_api order submission | **유지 (preserve)** → optional R7 (needs SDK check) |

### ✅ User decision (2026-06-06): **Preserve all three** (option (a))
R3 extraction is therefore **FULLY T1** — zero behavior change. The 3 divergences stay as small
subclass hooks/overrides so each broker keeps its exact current behavior:
- T3-1 → base exposes an abstract `_alpaca_side(order.side)` hook; `AlpacaBroker` returns the
  correct full mapping, `BrokerApiBroker` returns its current `BUY if ==BUY else SELL` (bug preserved).
- T3-2 → base calls `self._time_in_force(order)`; each subclass keeps its current resolver.
- T3-3 → base `_build_request` calls a `_extras(order)` hook + a `_supports_trailing` flag;
  `AlpacaBroker` provides extras+trailing, `BrokerApiBroker` overrides `_extras→{}` and omits trailing.

The bug-fix (T3-1) + fail-closed TIF (T3-2) are filed as follow-up track **R7** so the *restructure*
and the *behavior fix* never ride in one commit.

## 정지 지점
- [x] T3 항목 식별 (T3-1/2/3)
- [x] T3 항목 사용자 제시 완료 (UAQ)
- [x] 사용자 결정 반영 (preserve all) + audit.md 기록 완료 + R7 follow-up 생성
- [x] 단계 1 Alpaca-side 특성화 테스트 작성 + green (`tests/test_alpaca_broker.py`, 36 tests)
- [x] 단계 3 redesign (`3-redesign.md`)
- [x] 단계 4 구현 (`4-implementation.md`) — full suite 1014 passed

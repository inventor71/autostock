# Stage 4 — Implementation: AlpacaShapedBroker extraction

**Track**: R3 · **Branch**: refactor/R3 (worktree) · **Date**: 2026-06-06 · **Tier**: T1 (behavior-preserving)

## What landed
| File | Before | After | Change |
|------|-------:|------:|--------|
| `src/execution/brokers/_alpaca_shaped.py` | — | 516 | **NEW** shared template-method base |
| `src/execution/brokers/alpaca_broker.py` | 602 | 250 | thin Trading-API subclass |
| `src/execution/brokers/broker_api_broker.py` | 593 | 265 | thin Broker-API subclass |
| **two-broker total** | **1195** | **1031** | −164 LOC, and the ~450 *duplicated* lines now have a single source of truth |
| `tests/test_alpaca_broker.py` | — | NEW | 36 Alpaca-side characterization tests (closed the Stage-1 gap) |
| `tests/test_broker_api_broker.py` | — | +fixture | `_fresh_impl` mirrors new `__init__` (assertions unchanged) |

## How (template method)
`AlpacaShapedBroker(BaseBroker)` owns the shared algorithm: `_build_request`, `submit_order`,
`_poll_for_fill`, `get_order_status`, `cancel_order`, `close_position`, `get_position`,
`get_all_positions`, `get_portfolio_state`, `is_market_open`, `is_shortable`, `get_open_orders`,
`get_latest_prices`, the `_position_side`/`_to_open_order` mappers, and the two module constants.
Subclasses provide only thin `_do_*` client hooks + the SDK request-envelope **class attrs** +
`_open_orders_status`. `get_fills`/`_to_fill_event*`, `record_trade_ledger`, and Alpaca's native
`replace_order`/`cancel_all_orders` stayed in the subclasses (genuinely different, not duplicated).

## Behavior preservation (the 3 divergences — preserved per the T3 decision)
- **T3-1** `_alpaca_side`: base default = correct mapping (AlpacaBroker uses it); `BrokerApiBroker`
  overrides with its current `BUY if ==BUY else SELL` — the `BUY_TO_COVER→SELL` quirk is preserved.
- **T3-2** `_time_in_force`: base = F9 fail-closed (AlpacaBroker); `BrokerApiBroker` overrides with
  its gtc→GTC else→DAY downgrade.
- **T3-3** `_extras`/trailing: base `_extras={}` + `_req_trailing=None` (BrokerApiBroker);
  AlpacaBroker overrides `_extras` (extended_hours/client_order_id) and sets `_req_trailing`.
→ Each broker produces byte-identical SDK requests, the same client-call sequence, and the same
returns/exceptions as before. Fixes for T3-1/T3-2 are carved into track **R7**.

## Note on `__new__`-constructed test instances
Several tests build a broker via `Broker.__new__(Broker)` (bypassing `__init__`). The original
`_build_request` referenced module-level request classes, so those instances worked. To preserve
that, the request-envelope classes are **class attributes** (not instance attrs); only the
open-orders query enum is set in `__init__`. `test_broker_api_broker._fresh_impl` was updated to set
the same attrs the new `__init__` sets (fixture mirror — no assertion changed).

## Verification
- `tests/test_alpaca_broker.py` + `test_execution.py` + `test_broker_api_broker.py` +
  `test_human_order_gate.py` + `test_kis_broker.py` → **141 passed**.
- **Full suite** `pytest -q` → **1014 passed, 0 failed** (was 978 + 36 new = 1014).
- `py_compile` clean; no external references to the moved constants
  (`_ALPACA_TO_ORDER_TYPE` / `_TERMINAL_STATUSES`).

## Post-merge guide: SKIPPED (purely internal)
No observable production behavior change — internal class hierarchy only. Broker selection, order
flow, RiskManager/DecisionExecutor/sidebar all unchanged. Per build-and-test.md Step 7.5, the
post-merge guide is skipped for purely-internal changes.

## Critic pass (independent review)
Ran the `critic` subagent against the originals at `ec2875c` (method-by-method). It verified all 7
focus areas byte-identical (side mapping, get_open_orders seen/terminal ordering, _build_request
extras/trailing/raise, ImportError fallbacks, no lost symbols, is_market_open/is_shortable/
latest-prices/ledger/replace/cancel-all). Findings:
- **[MEDIUM] fixed**: the *preserved* broker_api quirks (T3-1 side, T3-2 TIF) had no characterization
  tests — only AlpacaBroker's base behavior was tested, so dropping the broker_api overrides would
  flip behavior with CI still green. Added `TestPreservedSideMapping` + `TestPreservedTimeInForce`
  to `tests/test_broker_api_broker.py` (8 tests) asserting the current quirk; R7 must consciously
  flip those assertions. Full suite now **1022 passed**.
- **[LOW] accepted**: base uses `getattr(settled, "filled_avg_price", None)` for both brokers where
  OLD AlpacaBroker used direct attribute access — only observable if the SDK returns an object
  missing the field, which alpaca-py never does (fields are always defined, None-valued at worst).
  Accepted as harmless hardening, not a prod-observable change.
- **[LOW] accepted**: AlpacaBroker data-client is now assigned only after `_make_data_client`
  returns, so a (never-occurring) `install_session_timeout` failure rebuilds next call instead of
  caching a timeout-less client. Negligible / arguably better.

## Pre-merge re-sweep (refactor-track discipline)
Before merging, re-diff `main` since base `ec2875c` for any NEW broker code that re-introduces the
duplication this track removed (e.g. a third Alpaca-shaped broker, or methods copy-pasted between
the two). Fold qualifying hits in or record as a followup. (concurrent-tracks.md lifecycle §3.)

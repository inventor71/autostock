# F16 — Functional Design (unit `broker-api-adapter`)

**Stage**: CONSTRUCTION → Functional Design
**Status**: awaiting approval
**Base commit**: cc125e5
Grounded against `src/execution/base.py` (port) + `src/execution/brokers/alpaca_broker.py`
(reference impl) + verified `BrokerClient` signatures (alpaca-py 0.43.2).

## 1. Component

One new class **`BrokerApiBroker(BaseBroker)`** in `src/execution/brokers/broker_api_broker.py`,
bound at construction to a single `account_id` and a `BrokerClient(sandbox=True)`. No new domain
entities — it reuses the existing core models (`Order`, `FilledOrder`, `OpenOrder`, `Position`,
`PortfolioState`, `FillEvent`). No new port methods; it fills the same `BaseBroker` surface
`AlpacaBroker` does, so RiskManager / DecisionExecutor / agent / F8 sidebar consumers are untouched.

```
RiskManager ─▶ BaseBroker(port) ─┬─ AlpacaBroker      (TradingClient, paper, 1 own account)
                                 └─ BrokerApiBroker   (BrokerClient.sandbox, *_for_account, account_id)   ← NEW
```

## 2. Confirmed design decisions (FD Q&A, 2026-05-31)

| # | Decision |
|---|----------|
| **Funding** | **Separated from the adapter.** Add a `--fund <amount>` action to `scripts/broker_create_accounts.py` (one-time setup: create ACH relationship → ACH transfer; sandbox clears it — **timing to confirm at V3**, not assumed instant). The adapter does NOT fund; with buying_power 0 a buy simply fails like any broker rejection. Keeps the trading object free of funding side-effects (clean separation; no conflict with SECURITY-15). |
| **Selection** | `settings.yaml` gains `broker.provider: alpaca \| broker_api` (default `alpaca`); `account_id` from env `BROKER_ACCOUNT_ID`. `main.py` constructs the chosen impl. |

## 3. Method mapping (BaseBroker → BrokerClient)

All trading calls pass `self._account_id`. `self._c = BrokerClient(key, secret, sandbox=True)`.

| BaseBroker method | Broker API call | Notes |
|---|---|---|
| `submit_order(Order)` | `submit_order_for_account(account_id, order_data)` then poll `get_order_for_account_by_id` | Reuse AlpacaBroker's `_build_request` / `_time_in_force` / `_poll_for_fill` logic. **Mixed imports (verified, critic #2):** order *envelope* classes (Market/Limit/Stop/StopLimit) from **`alpaca.broker.requests`** — they carry `order_class`/`take_profit`/`stop_loss`/`legs` — but the bracket/OCO **legs `TakeProfitRequest`/`StopLossRequest` from `alpaca.trading.requests`** (broker.requests has neither). V-impl-1 **RESOLVED**: broker `MarketOrderRequest` exposes `order_class`+`take_profit`+`stop_loss`+`legs`. Returns broker `Order` → same `FilledOrder` mapping. |
| `get_order_status(id)` | `get_order_for_account_by_id(account_id, id)` | Same `FilledOrder` mapping; None on error. |
| `cancel_order(id)` | `cancel_order_for_account_by_id(account_id, id)` | Returns bool; warn+False on error (parity). |
| `get_position(symbol)` | `get_open_position_for_account(account_id, symbol)` | Returns trading `Position` → same `Position` mapping; None if absent. |
| `get_all_positions()` | `get_all_positions_for_account(account_id)` | Same `Position` list mapping; raises `BrokerError` on failure (parity). |
| `get_portfolio_state()` | `get_trade_account_by_id(account_id)` (cash/equity) + `get_all_positions()` | `TradeAccount.cash/equity` → `PortfolioState`. |
| `close_position(symbol)` | `close_position_for_account(account_id, symbol)` then poll | Same `FilledOrder` mapping; None on error (parity). |
| `get_open_orders(symbol?)` | `get_orders_for_account(account_id, GetOrdersRequest(status=OPEN, nested=True))` | Reuse `_to_open_order` + leg-flattening verbatim (broker returns the same Order shape). |
| `is_market_open()` | `get_clock()` (broker-level, no account) | Reuse retry/fail-closed loop verbatim. |
| `get_fills(since?)` | `get_account_activities(GetAccountActivitiesRequest(account_id=…, activity_types=[FILL], after=since), handle_pagination=PaginationType.FULL)` | Returns **typed `TradeActivity`** models, NOT dicts. **Do NOT reuse the dict parser** `_to_fill_event` (`alpaca_broker.py:299`, uses `a.get(...)`/`a["id"]`/`a.get("date")` — would throw on every row; critic #1). Write a typed mapper `_to_fill_event_typed(a)` using attributes: `a.id`, `a.symbol`, `str(a.side).split(".")[-1].lower()` (side is an enum), `a.qty`, `a.price`, `a.transaction_time`; guard with `isinstance(a, TradeActivity)` (filter out `NonTradeActivity`). Keyed by activity `id` (partial-fill-safe, idempotent). **Pass `handle_pagination=FULL`, no `max_items_limit`** (critic #7 — else fills silently truncate and the cursor skips them). Best-effort → [] on failure (NFR-4). |
| `get_latest_prices(symbols)` | Market Data API w/ broker Basic-auth at sandbox data host | See §4 (**V1**). Best-effort → {} on failure. |
| `record_trade_ledger(path,…)` | `record_trades(shim, path,…)` | `record_trades` calls `client.get_orders(filter=…)`; BrokerClient has only `get_orders_for_account`. Pass a tiny **shim** exposing `.get_orders(filter=)` → `get_orders_for_account(account_id, filter)`. No change to `trades_log.record_trades`. |

## 4. Market data (FR-6 / V1) — mechanism resolved; only data-availability open

`BrokerClient` exposes **no** market-data method, but `StockHistoricalDataClient` already has
first-class params for this (verified, critic #3): its `__init__` is
`(api_key, secret_key, oauth_token, use_basic_auth=False, raw_data=False, url_override=None,
sandbox=False)`. Design:
- Build it as **`StockHistoricalDataClient(broker_key, broker_secret, use_basic_auth=True,
  url_override="https://data.sandbox.alpaca.markets")`** (or `sandbox=True`). **No raw GET / auth
  investigation needed.** Do **NOT** copy AlpacaBroker's positional construction
  (`alpaca_broker.py:333` — `StockHistoricalDataClient(self._api_key, self._secret_key)` uses
  header auth + the **prod** host → 401 with broker creds).
- `get_latest_prices` body otherwise mirrors AlpacaBroker (`StockLatestTradeRequest`).
- **V1 live-verify** is now scoped to *data availability only*: does sandbox return usable latest
  prices for the universe? If not, fall back to the existing `data_provider` with Trading keys
  (contingency, not default per Q2).
- Read-only, best-effort, failure → `{}` (NFR-4); never blocks trading.

## 5. Business rules

- **BR-1 (fail-closed init, SECURITY-15)**: ctor requires non-empty broker creds **and**
  `account_id`; missing/blank → raise `BrokerError` (never start, never silently fall back to
  AlpacaBroker / Trading API).
- **BR-2 (account binding)**: every trading call is scoped to `self._account_id`; the id is
  validated at init (`get_trade_account_by_id` succeeds) so a bad id fails fast.
- **BR-3 (no secrets in logs, SECURITY-03)**: log the account *number* or a masked id only —
  never the key/secret/full UUID in info logs. `__init__` logs `BrokerApiBroker initialized
  (account=…masked…, sandbox=True)`.
- **BR-4 (pure execution port, SECURITY-11)**: no risk/sizing/funding logic in the adapter; it
  only translates calls. (Funding lives in the farm script.)
- **BR-5 (behaviour parity)**: fill-poll timeout/interval, GTC for bracket/OCO legs, terminal-status
  set, error→warn-and-return-empty vs raise — all identical to AlpacaBroker so downstream behaviour
  is unchanged (FR-8).
- **BR-6 (fills idempotency)**: `get_fills` keys on activity `id`; `since` is the `transaction_time`
  cursor; dedup-by-id covers the same-timestamp boundary (parity with the F3 contract); requests
  `handle_pagination=FULL` so the cursor never advances past an unreturned page (critic #7).
- **BR-7 (private-attr coupling is NOT covered, critic #5)**: the "downstream untouched" claim
  (FR-7/§1) holds for the `BaseBroker` *port* consumers. It does **not** extend to code that reaches
  into `broker._client` assuming a `TradingClient` — notably `scripts/status.py:180-181`
  (`client = broker._client` → `render(...)`). status.py hardcodes `AlpacaBroker`, so this is **not
  a regression** for F16, but pointing status/F8 sidebar at `broker_api` later would break until that
  private-attr reach-in is removed. Documented boundary; out of scope here.

## 6. Funding action (separated, in `scripts/broker_create_accounts.py`)

Real request shapes (verified, critic #4 — the two-line sketch was wrong):
- `create_ach_relationship_for_account(account_id, CreateACHRelationshipRequest(...))` **requires
  bank fields**: `account_owner_name, bank_account_number, bank_account_type, bank_routing_number,
  nickname` (dummy values for sandbox). **Capture the returned relationship `id`.**
- `create_transfer_for_account(account_id, CreateACHTransferRequest(relationship_id=<id>,
  amount=<amount>, direction=INCOMING, ...))` — `relationship_id` is **required** and must be
  threaded from step 1; also `timing`/`transfer_type` as the model requires.
- `--fund <amount>` (with `--account <id>` or apply to all): create-relationship-if-absent →
  transfer → re-read `buying_power`.
- **V3 live-verify**: confirm the sandbox transfer **clears** and `buying_power > 0` (timing is
  NOT assumed instant). The `create_journal` (firm/sweep-source) alternative was considered but
  needs a sweep/firm source account, so it is not simpler — ACH path chosen.

## 7. Out of scope / deferred

Multi-account orchestration; production broker host; OAuth credential types; backtest changes;
console/UI account switching. (Same as requirements §7.)

## 8. Implementation-verify checklist (resolved during Code Gen, gated at Build & Test)

- **V-impl-1 — RESOLVED (critic #2)**: broker `MarketOrderRequest`/`LimitOrderRequest` carry
  `order_class`/`take_profit`/`stop_loss`/`legs`; legs come from `alpaca.trading.requests`. Bracket/
  OCO supported with the mixed-import pattern in §3.
- **V1 — data availability only (critic #3)**: auth/host mechanism resolved
  (`use_basic_auth=True, url_override=…`); live-verify only that sandbox returns usable prices.
- **V3**: sandbox ACH funding clears → buying_power > 0 (timing not assumed instant).
- **Carried boundary (critic #5)**: `broker._client` private-attr reach-ins (status.py) are out of
  scope and excluded from the parity claim (BR-7).

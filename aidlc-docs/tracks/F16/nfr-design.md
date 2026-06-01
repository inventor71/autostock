# F16 — NFR Design

**Stage**: CONSTRUCTION → NFR Design
**Status**: complete (awaiting approval as part of the Code Gen Part-1 gate)

## Patterns

- **P1 — Fail-closed construction (SECURITY-15)**: `BrokerApiBroker.__init__(api_key, secret_key,
  account_id, sandbox=True, …)` raises `BrokerError` if any of key/secret/`account_id` is blank, and
  validates the account by a single `get_trade_account_by_id(account_id)` call (bad id → fail fast,
  not at first trade). No fallback to AlpacaBroker / Trading API anywhere.
- **P2 — Lazy market-data client**: build `StockHistoricalDataClient(key, secret,
  use_basic_auth=True, url_override="https://data.sandbox.alpaca.markets")` on first
  `get_latest_prices` (mirror AlpacaBroker's lazy build, but with the sandbox/basic-auth params —
  NOT positional prod construction).
- **P3 — Secrets hygiene (SECURITY-03)**: a `_mask(account_id)` helper (first 8 chars + `…`) used in
  all logs; init logs account *number* (from the validated `TradeAccount`) + masked id only.
- **P4 — Error parity (NFR-3/NFR-4)**: abstract methods raise `BrokerError` on hard failure
  (submit/positions/portfolio), best-effort reads (`get_fills`/`get_latest_prices`/`get_open_orders`)
  warn+return-empty; `cancel`/`close`/`get_order_status` warn+return False/None — exactly mirroring
  `alpaca_broker.py`.
- **P5 — Pagination safety (BR-6)**: `get_account_activities(..., handle_pagination=
  PaginationType.FULL)`, no `max_items_limit`.
- **P6 — record_trade_ledger shim**: a small private `_LedgerClientShim` exposing only
  `get_orders(filter=)` → `self._c.get_orders_for_account(self._account_id, filter)`, passed to the
  unchanged `trades_log.record_trades`.

## Logical components / files

- **New**: `src/execution/brokers/broker_api_broker.py` — `BrokerApiBroker(BaseBroker)` + module-level
  request/model mappers (some reused from AlpacaBroker, some new: `_to_fill_event_typed`).
- **Edit**: `config/config.py` — `BrokerConfig.provider: str = "alpaca"`; `Settings` env fields
  `broker_api_key`, `broker_api_secret`, `broker_account_id` (default "").
- **Edit**: `config/settings.yaml` — `broker.provider: alpaca` (documented `broker_api` option).
- **Edit**: `main.py` `create_broker(settings)` (line 26) — branch on `settings.broker.provider`:
  `alpaca` → existing `AlpacaBroker`; `broker_api` → `BrokerApiBroker(broker_api_key,
  broker_api_secret, broker_account_id, sandbox=True)`.
- **Edit**: `scripts/broker_create_accounts.py` — `--fund <amount>` action (relationship + transfer).
- **Edit**: `.env.example` — note `BROKER_ACCOUNT_ID` (already has BROKER_API_KEY/SECRET).
- **Tests**: `tests/test_broker_api_broker.py` (mocked BrokerClient per method + PBT on mappers).

## Concurrency

The adapter is **synchronous** and called only from the existing broker call sites
(RiskManager → DecisionExecutor; the F2/F4 CommandWorker already serializes broker mutations).
It introduces **no new thread, lock, or background job** — same threading posture as `AlpacaBroker`.
NFR-1/NFR-2 invariants of the steering runtime are unaffected (it's a drop-in `BaseBroker`).

## Infrastructure Design — SKIP (local daemon, no cloud infra).

# F16 — NFR Requirements (minimal)

**Stage**: CONSTRUCTION → NFR Requirements
**Status**: complete (awaiting approval as part of the Code Gen Part-1 gate)

## Tech-stack decision: 0 new runtime deps

- `alpaca-py` 0.43.2 already present → `BrokerClient`, `alpaca.broker.requests`,
  `alpaca.trading.requests` (legs), `alpaca.trading.models.TradeActivity`,
  `alpaca.data.historical.StockHistoricalDataClient` (with `use_basic_auth`/`url_override`),
  `alpaca.broker.enums.ActivityType`, `alpaca.common.enums.PaginationType`.
- `pydantic`/`pydantic-settings` (config), `loguru` (logging) reused.
- Hypothesis already a dev dep (PBT). **No new runtime or dev dependency.**

## NFR targets

- **NFR-1 (Security, blocking)** — SECURITY-03/11/15 per requirements §5. Concretely:
  - fail-closed `__init__` (missing creds/`account_id` → `BrokerError`, no silent fallback);
  - never log key/secret/full account UUID (log masked id + account number);
  - adapter is a pure execution port (no risk/sizing/funding).
- **NFR-2 (Tested, PBT-Partial)** — Hypothesis on the pure mappers only
  (`_to_fill_event_typed`, order→request, position/account→model round-trips); example-based unit
  tests with a mocked `BrokerClient` for every `BaseBroker` method; **no live network in unit
  tests**. Live behaviour (V1/V3/V-impl-1) verified separately against an isolated farm account.
- **NFR-3 (Behaviour parity)** — fill-poll timeout/interval, GTC-for-protective-legs, terminal
  status set, raise-vs-warn error handling identical to `AlpacaBroker`.
- **NFR-4 (Best-effort reads)** — `get_fills`/`get_latest_prices`/`get_open_orders` never raise;
  failures → empty + warning log (parity with the F3/F8 contract).

## Deferred to NFR Design

Lazy-client construction pattern; pagination handling; account-id validation at init; where the
provider switch lives (config vs main.py); concurrency placement (adapter runs inside the existing
serialized command path — confirm no new primitive needed).

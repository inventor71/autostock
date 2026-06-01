# F16 — Broker API Adapter: Requirements

**Stage**: INCEPTION → Requirements Analysis (Standard depth)
**Status**: awaiting approval
**Base commit**: cc125e5

## 1. Intent / Problem

We can now create unlimited simulated Alpaca accounts via the **Broker API sandbox**
(`scripts/broker_create_accounts.py`, commit `cc125e5`; 5 accounts already APPROVED). But the
bot's execution layer only knows how to trade **one** account through the **Trading API**:
`BaseBroker` (port, `src/execution/base.py`) has a single real implementation `AlpacaBroker`
(`TradingClient(api_key, secret_key, paper=)`, `src/execution/brokers/alpaca_broker.py`).

To actually run a strategy *inside* a Broker-API sandbox account, we need a new `BaseBroker`
implementation that talks to `BrokerClient` per-account endpoints (`*_for_account`, addressed by
`account_id`) instead of `TradingClient`. That is this track.

Related: memory [[broker-api-sandbox-account-farm]]. Locked-architecture context:
[[llm-trader-redesign]] (advisor-only; the broker is the mechanical execution port),
[[risk-execution-redesign]] (RiskManager → Broker is the sole order gate).

## 2. Confirmed Decisions (Requirements Q&A, 2026-05-31)

| # | Decision | Choice |
|---|----------|--------|
| Q1 | **Scope** | **Single-account adapter** — one new `BaseBroker` impl trading one `account_id`; `main.py` can select it instead of `AlpacaBroker`. NOT a multi-account orchestrator (deferred). |
| Q2 | **Market data source** | **Broker API data endpoints** — fetch prices via the Market Data API using the **same broker Basic-auth creds**; do NOT depend on separate Trading API keys. |
| Sec | **Security Baseline** | **Enabled** (blocking). |
| PBT | **Property-Based Testing** | **Partial** (pure functions / serialization only; Hypothesis). |

## 3. Assumptions (stated defaults — confirm at the gate; raise to change)

- **A1 — Account selection**: the traded account is chosen by **env `BROKER_ACCOUNT_ID`**
  (a UUID from the farm). One account per process. (No CLI flag / auto-pick in v1.)
- **A2 — Auth**: reuse the existing `BROKER_API_KEY` / `BROKER_API_SECRET` (Legacy, Basic auth)
  already in `.env`. Sandbox-only (`BrokerClient(sandbox=True)`); the prod broker host is out of
  scope.
- **A3 — Method parity**: implement the **full `BaseBroker` surface that `AlpacaBroker` provides**
  (submit_order, get_order, cancel_order, get_open_position / get_all_positions, get_account /
  equity, account-activities/fills, close_position, market clock / is_market_open,
  `record_trade_ledger`, `get_latest_price`). No new port methods.
- **A4 — Selection mechanism**: a small factory/branch in `main.py` (e.g. `broker.provider:
  alpaca | broker_api` in settings, or env) picks the impl. No change to `BaseBroker`'s contract,
  so RiskManager / DecisionExecutor / agent paths are untouched.
- **A5 — Backtest unaffected**: `SimulatedBroker` and the backtest path are out of scope.

## 4. Functional Requirements

- **FR-1** A new `BaseBroker` implementation (working name `BrokerApiBroker`) backed by
  `alpaca.broker.BrokerClient(sandbox=True)`, bound to one `account_id` at construction.
- **FR-2** All order operations route through the per-account endpoints:
  `submit_order_for_account`, `get_order_for_account_by_id`, `cancel_order_for_account_by_id`,
  `replace_order_for_account_by_id` (if used by bracket/replace logic), preserving the existing
  RiskManager → Broker order contract (request/response shapes the executor expects).
- **FR-3** Positions / account: `get_open_position_for_account`, `get_all_positions_for_account`,
  `get_trade_account_by_id` (equity/cash), `close_position_for_account`,
  `close_all_positions_for_account`, mapped to the same `BaseBroker` return types AlpacaBroker uses.
- **FR-4** Fills / trade ledger: `get_account_activities` (FILL) → the same shape the existing
  activities/fills path and `record_trade_ledger` consume.
- **FR-5** Market clock: `get_clock` → `is_market_open`.
- **FR-6** `get_latest_price(symbol)` via the **Market Data API** using broker Basic-auth creds,
  pointed at the sandbox data host `https://data.sandbox.alpaca.markets/{version}` (see V1).
- **FR-7** Selection: `main.py` can construct `BrokerApiBroker` (account from `BROKER_ACCOUNT_ID`)
  in place of `AlpacaBroker` without touching downstream consumers (A4).
- **FR-8** Output parity: the bot's logging / round-trip / ledger behaviour is unchanged when
  running on the Broker adapter (same `BaseBroker` semantics).

## 5. Non-Functional Requirements

- **NFR-1 (Security, blocking)**: SECURITY-03 (no broker key/secret/account_id secrets in logs —
  log only the account *number* or a masked id), SECURITY-11 (auth/risk isolation — adapter is a
  pure execution port, no risk logic), SECURITY-15 (fail-closed: missing `BROKER_ACCOUNT_ID` /
  creds → refuse to start, never fall back to a wrong account or to the Trading API silently).
  Other SECURITY rules N/A (no web app, DB, IaC, user auth).
- **NFR-2 (Tested)**: PBT-Partial via Hypothesis on any pure mapping/serialization helpers
  (e.g. response → `BaseBroker` model). Example-based unit tests (mocked `BrokerClient`) for each
  mapped method; no live network in unit tests.
- **NFR-3 (No new runtime deps)**: `alpaca-py` (BrokerClient) already present; reuse stdlib +
  existing libs. To confirm in NFR Requirements.

## 6. Feasibility / Verification Items (live, paper-equivalent)

- **V1 — Market data on broker creds in sandbox**: docs say the same broker creds work with the
  Market Data API via HTTP Basic auth, sandbox host `data.sandbox.alpaca.markets`. `BrokerClient`
  itself exposes **no** market-data method (verified: only `*_for_account` trading/account
  methods), so FR-6 needs either a `StockHistoricalDataClient` pointed at the sandbox data host
  with broker creds, or a small raw GET. **Must live-verify** that sandbox returns a usable latest
  price for the universe symbols (sandbox data may be limited/delayed). This is the main open risk.
- **V2 — Order lifecycle in sandbox**: submit → fill → activities(FILL) → position/equity update
  must round-trip for a real bracket order against a farm `account_id`. Live smoke (read-mostly
  plus one tiny order) against an isolated sandbox account.
- **V3 — Funding**: a fresh sandbox account may have **zero buying power** until simulated funding;
  may need a `create_transfer_for_account` (sandbox instant) step to place buys. Confirm in design.

## 7. Out of Scope (deferred)

- Multi-account orchestration (Q1-B): running N strategies/daemons across N accounts.
- Production Broker API (real KYC/funds), OAuth `Client Secret`/JWT credential types.
- Backtest / `SimulatedBroker` changes.
- A console/UI surface for account switching.

## 8. Extension Configuration (F16)

- **Security Baseline**: **Enabled** (enforce, blocking). Applicable: SECURITY-03, 11, 15.
  N/A: web/DB/IaC/user-auth rules (none in this adapter).
- **Property-Based Testing**: **Partial** — Hypothesis, pure mapping/serialization helpers only;
  other rules advisory. Consistent with the project-wide config and F2/F3.

## 9. Stage determination (proposed; finalized in Workflow Planning)

- User Stories — **SKIP** (internal execution-layer addition, no user-facing UI; consistent with
  prior internal tracks).
- Application Design — likely **SKIP** (no new component topology; one new class behind an
  existing port) — fold into Functional Design.
- Units Generation — **SKIP** (single cohesive unit `broker-api-adapter`).
- Construction: Functional Design (light) → NFR Requirements (minimal) → NFR Design → Code
  Generation → Build & Test, with a live-verify gate for V1–V3.

# Track F16 — Broker API adapter (trade the sandbox account farm)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F16
- **Title**: Broker API adapter — let the bot trade the Broker-API sandbox accounts
- **Type**: feature
- **Branch**: feat/F16 (TBD — created at Code Gen Part 2)
- **Worktree**: .claude/worktrees/F16 (TBD)
- **Submodule branch**: — (no operator-console/cli change expected)
- **Base commit**: cc125e5
- **Start Date**: 2026-05-31T04:42:28Z
- **Status**: active

## Extension Configuration
- **Security Baseline**: Enabled (blocking). Applicable: SECURITY-03 (no creds/account_id in
  logs), SECURITY-11 (auth/risk isolation; adapter = pure execution port), SECURITY-15
  (fail-closed on missing creds/account). Others N/A (no web/DB/IaC/user-auth).
- **Property-Based Testing**: Enabled — **Partial** (Hypothesis; pure mapping/serialization
  helpers only). Consistent with project-wide config + F2/F3.

## Scope
Background: F-less PoC `scripts/broker_create_accounts.py` (committed `cc125e5`) creates N
simulated Alpaca accounts via the **Broker API sandbox** (`BrokerClient`, Legacy key, Basic
auth) — bypassing the Trading API's 3-paper-per-owner limit. See memory
[[broker-api-sandbox-account-farm]]. But the bot's execution layer (`BaseBroker` port,
`src/execution/base.py`) is implemented only by `AlpacaBroker` (Trading API,
`TradingClient(paper=)`, one "my" account). To actually run strategies inside those farm
accounts we need a **Broker-API-backed `BaseBroker` implementation** that addresses a chosen
`account_id` via `BrokerClient` per-account endpoints.

Integration surface: `BaseBroker` (port), `AlpacaBroker` (reference impl,
`src/execution/brokers/alpaca_broker.py`), broker wiring in `main.py`.

## Stage Progress
- [x] Workspace Detection — brownfield, RE artifacts reused
- [x] Requirements Analysis — Standard depth; Q1=single-account adapter, Q2=Broker API data
      endpoint, Security=Enabled, PBT=Partial. Doc: `requirements.md`. **APPROVED 2026-05-31.**
- [x] User Stories — SKIP (internal execution-layer addition, no user-facing UI)
- [x] Workflow Planning — execution-plan.md; **APPROVED 2026-05-31**
- [x] Application Design — SKIP (one new class behind existing port; fold into Functional Design)
- [x] Units Generation — SKIP (single cohesive unit `broker-api-adapter`)
- [~] Construction (per-unit Code Generation) — unit `broker-api-adapter`
  - [x] Functional Design — functional-design.md; Funding=separated(`--fund`), Selection=
        settings.yaml `broker.provider`+env. **/critic: 7 findings (2 HIGH), all valid, folded in**
        (typed TradeActivity mapper #1; mixed broker/trading order-request imports #2→V-impl-1
        resolved; StockHistoricalDataClient use_basic_auth/url_override #3→V1 de-escalated; funding
        request shapes #4; status.py broker._client boundary BR-7 #5; pagination=FULL #7).
        **APPROVED 2026-05-31.**
  - [x] NFR Requirements (minimal) — nfr-requirements.md; 0 new deps; SECURITY-03/11/15 + PBT-Partial.
  - [x] NFR Design — nfr-design.md; P1–P6 (fail-closed init, lazy basic-auth data client, secrets
        mask, error parity, pagination=FULL, ledger shim); sync adapter, no new concurrency primitive.
        Infra Design SKIP.
  - [x] Code Generation **Part 1 (plan)** — code-generation-plan.md (Steps 0–11). **APPROVED 2026-05-31.**
  - [x] Code Generation **Part 2** — Steps 0–10 complete in worktree `.claude/worktrees/F16`
        (branch feat/F16):
        - Worktree created via `worktree-setup.sh F16 --py`
        - `config/config.py`: BrokerConfig.provider, Settings env fields
        - `src/execution/brokers/broker_api_broker.py`: 350+ lines, fail-closed init,
          mixed imports (broker envelopes + trading legs), full BaseBroker parity
        - `main.py`: create_broker() branch on `broker.provider == "broker_api"`
        - `scripts/broker_create_accounts.py`: `--fund` action (ACH + TransferDirection)
        - `.env.example`: BROKER_ACCOUNT_ID
        - `tests/test_broker_api_broker.py`: 34 tests (mocked + PBT), all green
        - Full regression: **448/448 green** (no AlpacaBroker-path breakage)
        - **Fix during impl**: `FundingDirection` → `TransferDirection` (correct enum name)
  - [~] **Live-verify (Step 11)**:
    - [x] **V3** — `--fund $1` on account `8eec141b`: transfer created (INCOMING, IMMEDIATE,
          SENT_TO_CLEARING). Original funding transfers all COMPLETE. Mechanism verified.
    - [x] **V1** — Broker API Market Data (sandbox): `get_latest_prices` verified (AAPL=$311.48,
          MSFT=$448.17, TSLA=$435.08). Basic-auth via StockHistoricalDataClient(use_basic_auth=True,
          url_override) works. Bug fix: store api_key/secret_key as instance attrs (BrokerClient
          doesn't expose them publicly). Fail-safe: empty symbols→{}, bad symbol→{}.
    - [x] **V-impl-1 partial** — Order lifecycle verified off-hours: LIMIT BUY accepted→
          status=accepted→canceled; get_open_orders leg-flattening; get_order_status;
          fail-closed on bad symbol. **Bracket/OCO fill round-trip pending market open**
          (ET 00:52 Mon Jun 1 → opens 09:30 ET).
    - [x] **Error handling**: bad account_id→APIError, empty api_key→BrokerError, bad symbol→
          BrokerError, account_id masked in logs (SECURITY-03).
    - [x] **Market clock**: is_market_open=False (correct for 00:52 ET), retry+fail-closed.
    - [x] **Regression**: 448/448 green after credential fix (commit b2be961).
  - [x] **Bug fix**: `get_latest_prices` was broken — `self._c.api_key` doesn't exist on
        BrokerClient. Fixed by storing `_api_key`/`_secret_key` in `__init__` and referencing
        those in the lazy StockHistoricalDataClient construction.
- [ ] Build & Test

# F16 — Workflow Planning / Execution Plan

**Stage**: INCEPTION → Workflow Planning
**Status**: awaiting approval
**Base commit**: cc125e5

## Stage determination (adaptive)

| Stage | Decision | Rationale |
|-------|----------|-----------|
| Reverse Engineering | SKIP (reuse) | Brownfield; artifacts already exist. |
| Requirements Analysis | DONE | Standard depth; approved 2026-05-31. |
| User Stories | **SKIP** | Internal execution-layer addition; no user-facing UI/workflow. |
| Workflow Planning | THIS | — |
| Application Design | **SKIP** | No new component topology — one new class behind the existing `BaseBroker` port; folded into Functional Design. |
| Units Generation | **SKIP** | Single cohesive unit. |
| **Construction (unit `broker-api-adapter`)** | EXECUTE | Functional Design → NFR Req (minimal) → NFR Design → Code Gen → Build & Test. |
| Infrastructure Design | **SKIP** | Local daemon; no cloud infra. |

## Risk assessment

- **Overall: Medium.** The adapter sits on the **live order path** (RiskManager → Broker), but it
  is *additive* — `AlpacaBroker` and the Trading API path are untouched, selection is opt-in via
  `BROKER_ACCOUNT_ID` / a provider switch (A4). Rollback = don't select it. Worktree-isolated.
- **Top risks** (carried from requirements):
  - **V1 (market data on broker creds, sandbox)** — `BrokerClient` has no market-data method;
    FR-6 hits the Market Data API with broker Basic-auth at `data.sandbox.alpaca.markets`. Sandbox
    data availability/latency unverified → **live-verify before declaring done**.
  - **V3 (buying power / funding)** — a fresh sandbox account may need `create_transfer_for_account`
    (instant sandbox funding) before buys succeed. Resolve in Functional/NFR Design.
  - **Contract drift** — response shapes from `*_for_account` endpoints must map to the exact
    `BaseBroker` return types the executor/ledger expect (TradeActivity vs order-level, etc.).

## Construction unit: `broker-api-adapter`

Internal build sequence (refined in Functional/NFR Design + Code Gen plan):
1. `BrokerApiBroker(BaseBroker)` skeleton bound to `account_id`; `BrokerClient(sandbox=True)` ctor;
   fail-closed on missing creds/account (NFR-1/SECURITY-15).
2. Order ops → `*_order_for_account` mapped to the executor's expected request/response.
3. Positions / account / close → `*_for_account`, mapped to `BaseBroker` models.
4. Activities/fills (`get_account_activities` FILL) → fills + `record_trade_ledger`.
5. Market clock (`get_clock`) + `get_latest_price` via Market Data API (broker creds, sandbox host).
6. `main.py` selection (env/provider) without touching downstream consumers.
7. Funding helper for sandbox buying power if V3 requires it.
8. Tests: mocked-`BrokerClient` unit tests per method + PBT-Partial on pure mappers; live-verify
   V1–V3 against an isolated farm `account_id`.

## Construction approach

- **Worktree gate**: code only in `.claude/worktrees/F16` on branch `feat/F16` (created as the
  first action of Code Generation Part 2). No submodule change expected.
- **Autonomy**: after Functional Design approval, run Construction (code + tests) autonomously per
  [[feedback-autonomy-construction]]; stop only at the live-verify decision (needs real sandbox
  account + buying power) or a genuine fork.
- **No new runtime deps** target (confirm in NFR Requirements).

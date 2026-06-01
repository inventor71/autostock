# F16 — Code Generation Plan (Part 1)

**Stage**: CONSTRUCTION → Code Generation (Part 1 — plan)
**Status**: awaiting approval to enter Part 2 (Part 2's FIRST action = create the worktree)
**0 new runtime/dev deps.**

> **Worktree gate**: NO code is written until Part 2. Part 2 step 0 creates
> `.claude/worktrees/F16` on branch `feat/F16` (off `cc125e5`/current main) via
> `scripts/worktree-setup.sh F16 --py` (symlinks main `.env`, main venv for live checks).
> No submodule change → no submodule branch.

## Steps

- [ ] **0. Worktree** — `scripts/worktree-setup.sh F16 --py`; verify `.env` symlink + venv.
- [ ] **1. Config** — `config/config.py`: `BrokerConfig.provider: str = "alpaca"`; `Settings` env
      fields `broker_api_key`/`broker_api_secret`/`broker_account_id` (default ""). `config/
      settings.yaml`: `broker.provider: alpaca` + comment documenting `broker_api`. `.env.example`:
      note `BROKER_ACCOUNT_ID`.
- [ ] **2. Adapter skeleton** — `src/execution/brokers/broker_api_broker.py`:
      `BrokerApiBroker(BaseBroker)`, fail-closed `__init__` (P1) + `_mask`/account validation (P3),
      lazy attrs. Import envelopes from `alpaca.broker.requests`, legs from
      `alpaca.trading.requests` (critic #2).
- [ ] **3. Orders** — `submit_order` (reuse `_build_request`/`_time_in_force`/`_poll_for_fill`
      logic via `submit_order_for_account` + `get_order_for_account_by_id`), `get_order_status`,
      `cancel_order`, `get_open_orders` (reuse `_to_open_order` + leg flattening). Error parity (P4).
- [ ] **4. Positions / account / close** — `get_position`, `get_all_positions`,
      `get_portfolio_state` (`get_trade_account_by_id`.cash/.equity), `close_position`.
- [ ] **5. Fills + ledger** — `get_fills` via `get_account_activities(FILL,
      handle_pagination=FULL)` + NEW `_to_fill_event_typed` (attribute access, `isinstance
      TradeActivity` guard — critic #1); `record_trade_ledger` via `_LedgerClientShim` (P6).
- [ ] **6. Market data + clock** — `get_latest_prices` (lazy `StockHistoricalDataClient`
      `use_basic_auth=True, url_override=…` — P2/critic #3); `is_market_open` (`get_clock`, retry
      loop, no account arg).
- [ ] **7. Wiring** — `main.py` `create_broker` branch on `settings.broker.provider`.
- [ ] **8. Funding action** — `scripts/broker_create_accounts.py` `--fund <amount> [--account id]`:
      `create_ach_relationship_for_account` (dummy bank fields, capture `id`) →
      `create_transfer_for_account(CreateACHTransferRequest(relationship_id, amount,
      direction=INCOMING, …))` → re-read `buying_power` (critic #4).
- [ ] **9. Unit tests** — `tests/test_broker_api_broker.py`: mocked `BrokerClient` per method
      (assert correct `*_for_account` call + account_id + mapped return); fail-closed init tests;
      PBT-Partial (Hypothesis) on `_to_fill_event_typed` + order→request mapping. No live network.
- [ ] **10. Regression** — full suite green (no behaviour change to AlpacaBroker path).
- [ ] **11. Live-verify (gate, isolated farm account)** — V-impl-1 (bracket submit round-trips),
      V1 (sandbox latest price), V3 (`--fund` clears → buying_power>0 → a tiny buy fills →
      `get_fills`/positions/ledger reflect it). Stop here for the human decision if sandbox data or
      funding behave unexpectedly.

## Stop points (autonomy bounds)
- **Before Step 0** (this gate): user approves entering Part 2.
- **Step 11**: live-verify needs the real sandbox account + funding; report results before merge.

# F16 — Build & Test

> Single cohesive unit `broker-api-adapter`. Verification was performed live during Code Gen
> (see `evaluation-checklist.md`); this doc records the reproducible build/test procedure and the
> outcome on the **monorepo base** (`feat/F16` rebased onto `main` `2253029`, 2026-06-03).

## Prerequisites
- **Runtime**: Python 3.12, project `venv` at repo root (`venv/bin/python`).
- **Deps**: no new dependencies introduced by F16 (uses `alpaca-py` already pinned). Install via
  `pip install -r requirements.txt` if the env is fresh.
- **Env vars** (pydantic `Settings`, loaded from `.env` — worktree symlinks the main `.env`):
  - `BROKER_API_KEY`, `BROKER_API_SECRET` — Broker API sandbox Legacy key (Basic auth).
  - `BROKER_ACCOUNT_ID` — target farm account to trade.
  - Adapter is selected by `config/settings.yaml` → `broker.provider: broker_api`.

## Build
Pure-Python; no compile/bundle step. "Build success" = imports resolve and the suite collects.
```bash
venv/bin/python -c "import main; from src.execution.brokers.broker_api_broker import BrokerApiBroker"
```

## Unit tests
```bash
# from the F16 worktree
/home/jihoonpark/Project/autostock/venv/bin/python -m pytest tests/test_broker_api_broker.py -q
```
- **Expected**: 34 passed (mocked + Hypothesis PBT on `_to_fill_event_typed`).
- **Result (monorepo base, 2026-06-03)**: ✅ 34 passed.

## Full regression
```bash
/home/jihoonpark/Project/autostock/venv/bin/python -m pytest -q
```
- **Expected**: all green, no AlpacaBroker-path regression.
- **Result (monorepo base, 2026-06-03)**: ✅ **611 passed** (suite grew from 448 as F23 etc. landed
  on `main`; F16's 34 included).

## Integration / end-to-end (live sandbox)
Integration here = the adapter against the real Broker API sandbox farm account — already executed
and captured in `evaluation-checklist.md` (**25/25**). Key flows, re-runnable during market hours
against a funded farm account:
- Market BUY/SELL fills; **BRACKET (OCO)** round-trip (TP limit + SL stop both legs);
  `get_open_orders` surfaces HELD SL leg (B2 fix, `status=ALL`).
- Positions buy→position→sell→None; `close_position`; `get_fills` (8 fills / 3 round-trips);
  `record_trade_ledger` realized +$0.29.
- `get_latest_prices` via basic-auth `StockHistoricalDataClient` (B1 fix: creds stored in
  `__init__`); market-clock retry + fail-closed; error parity (bad account/key/symbol → fail-closed,
  account_id masked — SECURITY-03).

## Security & NFR check
- SECURITY-03 (no creds/account_id in logs): masked logging verified. ✅
- SECURITY-11 (adapter = pure execution port, no auth/risk logic): holds by construction. ✅
- SECURITY-15 (fail-closed on missing creds/account): init refuses; verified. ✅
- PBT-Partial: applied to pure mapper `_to_fill_event_typed`. ✅

## Gap analysis (Trading API → Broker API)
3 gaps, all **non-blocking**: `replace_order` (emulate cancel+resubmit), trailing stop (ADJUST_STOP
ratchet / unused by agent), native `cancel_all_orders` (N-call emulation works). Detail in
`evaluation-checklist.md` §8.

## Verdict
Build & Test **complete and green on the monorepo base**. F16 (`BrokerApiBroker`) is ready to merge.

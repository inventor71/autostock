# F9 — Build & Test Summary

Worktree: `.claude/worktrees/F9` (branch `feat/F9`). Base: a0b882d. Commits:
U-RISK `4db4771`, U-DAEMON `9eaf263`, U-CONSOLE `baf3cd2`.

## Automated results (GREEN)
| Suite | Command | Result |
|-------|---------|--------|
| Python (full) | `venv/bin/python -m pytest -q` | **414 passed** |
| Risk gate + Order + broker (U-RISK) | `pytest tests/test_human_order_gate.py` | 25 passed (incl. Hypothesis PBT, NFR-5) |
| Daemon structured verbs (U-DAEMON) | `pytest tests/test_steering_place_order.py` | 13 passed |
| Cross-language golden = live models | `pytest tests/test_steering_contract.py` | 4 passed |
| Console (TS) | `bun test ./test/` | **64 passed** (incl. per-verb args contract + structured path) |
| mcp-server build | `bun build src/mcp-server.ts` | clean (229 modules) |

## Coverage map → requirements
- **FR-1/FR-3** Alpaca-shaped tools + full param set — U-CONSOLE tools + Order model + broker mapping; trailing/extras request tests.
- **FR-2 (hybrid)** structured order tools added; parser.ts deterministic shorthand (incl. safety verbs + buy/sell) preserved.
- **FR-4** opencode `ask` per-tool permission keys documented in mcp-server.ts.
- **FR-5/FR-5a** `receive_human_order` budget/pool/breaker + clamp + auto-protect + price-sanity + `force`; `/buy` shorthand now gated.
- **FR-6** `OrderDecision` reason_code + message + suggestion; surfaced in outcome events.
- **FR-7** notional market+day only, else structured reject (handler + tests).
- **FR-8** cancel_order/cancel_all/replace_order/close_position/close_all; replace conservative (Q2=A).
- **NFR-1** advisor-only preserved — no new agent-reachable surface; tools only on console MCP.
- **NFR-2/SECURITY** zod boundary + PlaceOrderArgs `extra=forbid`; token never echoed (handleStructured test); unwired TIF/class fail-closed reject (no silent DAY downgrade).
- **NFR-3** golden `contract.json` extended with `command_args`; pinned both sides.
- **NFR-5** Hypothesis properties on clamp / no-oversell / unsupported-TIF.

## Live smoke (read-only) — PASSED 2026-05-31
Ran against the TEST paper account `PA3F5JU0T43K` ($1M paper equity), NO orders placed. Docker
wasn't usable in-session (user not in `docker` group, no passwordless sudo), so the harness's
read-only `run_smoke` logic was run directly via the main venv + worktree `.env.test`
(AUTOSTOCK_ENV_FILE), per the worktree-live-verification approach — equivalent verification.
- settings load TEST creds, `paper=True`; real `get_account()` read OK (ACTIVE).
- F9 broker read-only: `get_portfolio_state` / `get_open_orders`.
- F9 request mapping built against the LIVE SDK: `TrailingStopOrderRequest` (trail_percent) +
  `LimitOrderRequest` (ioc + extended_hours + client_order_id).
- `opg` TIF → `BrokerError` fail-closed reject (no silent DAY downgrade).
- `receive_human_order` vs the live $1M portfolio: 10M-share buy CLAMPED to 1000 (max_position_pct)
  with suggestion `{qty:1000}`.
- NOTE: `.env.test` lacks `EXPECTED_ACCOUNT_NUMBER` (harness warns, can't pin TEST account) —
  pre-existing config gap, not F9. Suggest pinning `EXPECTED_ACCOUNT_NUMBER=PA3F5JU0T43K`.

## Pending (user-gated)
- **Merge**: parent-repo `feat/F9` → main. No submodule gitlink change (fork untouched).
- **opencode.json**: add the 6 new `autostock_*` permission keys (`"ask"`) on the operator machine.

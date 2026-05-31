# F8 Build & Test — `console-sidebar-status-rich`

Worktree `.claude/worktrees/sidebar-status-rich`, branch `feat/console-sidebar-status-rich`
(parent `6c66a1f`, submodule `8fcb1ca`). **0 new runtime deps.** NOT merged/pushed.

## Build
- **Python**: no build step (interpreted). Import-smoke implicit in the test run.
- **Console (TS)**: bun. Full `tsgo` typecheck needs the submodule deps installed
  (`bun install` in `operator-console/cli`) — **NOT available in this env** (same limit as F5/F6;
  defer to the user's machine). The F8 changes are localized to the sidebar feature-plugin +
  one pure helper module + the width constant.

## Unit / regression tests
Runner: system `python3` / project `venv` (NOTE: `.venv` lacks pytest). Bun: `~/.bun/bin/bun`.

| Suite | Command | Result |
|-------|---------|--------|
| F8 daemon units | `python3 -m pytest tests/test_sidebar_status_rich.py` | **5 passed** |
| F6 sidebar (invested asserts updated) | `python3 -m pytest tests/test_sidebar_upgrade.py` | green |
| Full Python regression | `python3 -m pytest` | **371 passed, 0 failed** |
| Console pure helpers | `bun test sidebar-format.test.ts` | **6 pass, 0 fail** |

F8 test coverage:
- `test_sidebar_status_rich.py`: PriceBook TTL (fresh/stale/missing), account `invested`,
  `publish_snapshot` enrichment (held price reuse + PriceBook for non-held order symbols, side/role),
  `refresh_order_prices` fetches only non-held missing symbols, `refresh_recent_fills` sort-desc + cap-8.
- `sidebar-format.test.ts`: orderRole (status.py parity), orderTrigger, orderDelta (+ /0 guard),
  pnlPct, fmtPct (arrow+sign), fmtPrice, isUp boundary.

## Integration / performance
- Integration seams exercised by existing `test_steering_runtime.py` (publish path on the bus worker,
  snapshot file write) — green. No new cross-process seam (console reads `snapshot.json` as before).
- Performance: read-only UI. Added cost = two slow worker jobs (12s price fetch for non-held order
  symbols only; 45s recent_fills) + a few extra snapshot fields. No perf suite warranted (N/A).

## Security (Security Baseline)
- SECURITY-03: snapshot/cache carry prices/qty/symbols only — no secrets. (monitor.json log-tail
  masking unchanged from F6.)
- SECURITY-15: `get_latest_prices` and `get_fills` fetches are best-effort/fail-closed — a failure
  blanks Δ / hides the block, never aborts the snapshot publish or the scheduler.
- SECURITY-11: privilege separation unchanged (console read-only; order path advisor-only).

## Invariants held
Advisor-only; `decisions.jsonl → gate → RiskManager → Broker` unchanged; console reads `snapshot.json`
only (NFR-1); single CommandBus worker for all broker/data access (NFR-2); 0 new runtime deps;
additive fields are back-compatible (absent → block hidden, F6 BR-8).

## Pending before Operations (user-gated / env limit)
- **Daemon RESTART required** for the new blocks to appear (only the new daemon publishes the fields — F6 GOTCHA).
- tsgo typecheck (submodule deps) → user machine.
- Live: R1 holdings/orders/fills + color after restart; R2 non-held order-symbol Δ via PriceBook; R3 drag wrap + floor 36.
- Merge (submodule branch → fork main + push, then parent gitlink at merge) + push — outward, user gate.

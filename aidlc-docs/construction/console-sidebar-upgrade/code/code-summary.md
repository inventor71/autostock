# F6 console-sidebar-upgrade · Code Summary

**Worktree**: `.claude/worktrees/console-sidebar-upgrade`, branch `feat/console-sidebar-upgrade` (off main).
**Commits**: parent `e696630`; submodule `operator-console/cli` `82e009b` (re-pinned). 0 new runtime deps. NOT pushed/merged.

## Daemon (Python)
- `src/execution/base.py` — `BaseBroker.get_fills(*, since, min_notional) -> list[dict]` no-op default (FR-3 port, F3-aligned).
- `src/execution/brokers/alpaca_broker.py` — `get_fills` reuses tested `_alpaca_fills` (order-level fills via `get_orders`;
  sufficient for a realized-P&L summary, avoids the alpaca-py 0.43.2 raw-activities risk — deviation from the NFR "raw GET" note, simpler).
- `src/core/trades.py` — `summarize_today_round_trips(fills, *, now_et)` = `match_round_trips` + `_to_et` (UTC→ET `zoneinfo`)
  today filter → `{closed_count, win_rate, realized_pnl, as_of}`; empty→`win_rate=None` (critic #1/#4). Pure (PBT-tested).
- `src/agent/steering/runtime.py` — `publish_snapshot` adds `account` (via `_account_block` → reuses `equity_log.snapshot`,
  critic #5) + cached `round_trip`; `refresh_round_trip()` (worker, slow cadence, one broker `get_fills`); `publish_monitor()`
  → `steering/monitor.json` (turns/decisions/log summaries, secrets masked, SECURITY-03). Helpers `_turns_summary`/`_decisions_tail`/`_log_tail`/`_mask_secrets`.
- `src/trading/modes/agent.py` — registers `steering_roundtrip` (45s) + `steering_monitor` (10s) jobs.

## Console (TS, parent `operator-console/src/`)
- `parser.ts` — `READ_VERBS` += `turns`, `decisions` (read-only; no SteeringVerb/contract change).
- `filedrop.ts` — `monitorFile` + `readMonitor()`.
- `steer-handler.ts` — `handleSteerRead` dispatches `turns`/`decisions`/`log` → `monitor.json` (was: always snapshot — critic #3); `/status` etc still snapshot.
- `mcp-server.ts` — `steer_read` description updated (snapshot vs monitor verbs; account/round_trip noted).

## Console UI (TS, submodule `operator-console/cli`)
- `routes/session/sidebar-width.ts` (new) — shared reactive width signal (independent of `sidebarVisible`, critic #7),
  `loadWidth` (saved>env>42), debounced atomic `saveWidth` (XDG `~/.local/state/autostock-console/ui.json`), `clampWidth`.
- `routes/session/sidebar.tsx` — re-exports the signal (index.tsx `contentWidth` subscribes → single source); left-edge
  drag handle box `selectable={false}` (critic #2), `onMouseDrag` → `setSidebarWidth(dims.width − e.x, dims.width)`.
- `feature-plugins/sidebar/autostock.tsx` — account block (eq/cash/pnl, PnL color) + today round-trip line (empty state);
  hidden when fields absent (BR-8 back-compat).
- `routes/session/index.tsx` — **unchanged** (already calls the now-reactive `sidebarWidth()` in its `contentWidth` memo).

## Tests
- `tests/test_sidebar_upgrade.py` (+10): round-trip today/empty/UTC-ET-boundary + Hypothesis invariants; `get_fills` no-op;
  `_account_block` reuse; snapshot account/round_trip; `refresh_round_trip`; `publish_monitor` + secret masking. **Full suite 292 green.**
- `operator-console/test/steer-handler.test.ts` (+5): turns/decisions/log dispatch, no-monitor graceful, /status still snapshot. **bun 29 green.**

## Pending (user — cannot build the opencode TUI here)
- **R1**: `bun dev` live drag-resize — confirm handle owns capture (selectable=false), width persists across restart.
- **R4**: `get_fills` paper-account live check (today's round-trip summary populates intraday).
- Submodule TS not tsgo-typechecked here (deps uninstalled). Not pushed/merged. F5 merge: share the single width signal.

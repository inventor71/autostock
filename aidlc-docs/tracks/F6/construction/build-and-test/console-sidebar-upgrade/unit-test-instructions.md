# F6 console-sidebar-upgrade · Unit Test Instructions

## Python (pytest) — all green (292)
```bash
cd .claude/worktrees/console-sidebar-upgrade
venv/bin/python -m pytest tests/test_sidebar_upgrade.py -q     # F6-specific (10)
venv/bin/python -m pytest -q                                   # full regression (292)
```
F6 coverage (`tests/test_sidebar_upgrade.py`):
- `summarize_today_round_trips`: today-only filter, empty→`win_rate=None`, **UTC→ET boundary** (sell at UTC 02:00
  belongs to the prior ET day), Hypothesis invariants (`win_rate∈[0,1]`/`None`, `closed_count≥0`, `realized_pnl` float).
- `get_fills` no-op default on a non-Alpaca broker.
- `_account_block` reuses `equity_log.snapshot` (fields equity/cash/open_pnl/position_count).
- `publish_snapshot` includes `account` + `round_trip`; `refresh_round_trip` reads broker fills; `publish_monitor`
  writes `monitor.json` (turns/decisions) and masks a token in the log tail.

## TS — deterministic core (bun) — all green (29)
```bash
cd operator-console
~/.bun/bin/bun test test/steer-handler.test.ts test/filedrop.test.ts test/parser.test.ts test/contract.test.ts
```
> Run the **explicit files** — a bare `bun test` recurses into the submodule's own (un-built) test tree and errors on
> missing solid-js/@opencode-ai deps (unrelated to F6).
F6 coverage (`test/steer-handler.test.ts`): `/turns`,`/decisions`,`/log` dispatch to `monitor.json`; no-monitor graceful;
`/status` still returns the snapshot (not monitor).

## TS — submodule UI (tsgo) — USER step (deps uninstalled in AI env)
```bash
cd operator-console/cli && bun install && bunx tsgo --noEmit   # expect 0 errors
```
Covers `sidebar-width.ts` / `sidebar.tsx` / `autostock.tsx` types.

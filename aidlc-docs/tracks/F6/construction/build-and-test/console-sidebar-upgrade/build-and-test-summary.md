# F6 console-sidebar-upgrade · Build & Test Summary

| Suite | Command | Result |
|-------|---------|--------|
| Python full | `venv/bin/python -m pytest -q` | **292 passed** |
| Python F6 | `pytest tests/test_sidebar_upgrade.py` | **10 passed** (incl UTC/ET boundary + Hypothesis) |
| TS core (bun) | `bun test test/steer-handler.test.ts test/filedrop.test.ts test/parser.test.ts test/contract.test.ts` | **29 passed** (5 new) |
| TS submodule tsgo | `cd operator-console/cli && bun install && bunx tsgo --noEmit` | **USER** (deps uninstalled in AI env) |
| Live R1 (drag-resize+persist) | `bun dev` | ✅ **confirmed 2026-05-30** |
| Live R3 (`steer_read` view) / R4 (`get_fills` paper) | see integration doc | ⏳ later |

## Performance / Security
- **Performance**: N/A as a dedicated suite — read-only UI; new daemon work is one slow broker `get_fills` (45s job) +
  a file-only `monitor.json` write (10s). Snapshot publish 5s / console read 1.5s unchanged. No hot path touched.
- **Security (Security Baseline)**: SECURITY-03 — log tail masked (`_mask_secrets`), no token in any read view; SECURITY-11 —
  privilege separation unchanged (all F6 additions read-only, no order authority); SECURITY-15 — fail-closed (publish/IO
  failures skip+warn, sidebar hides absent fields). **PBT**: applied to the pure `summarize_today_round_trips` (Hypothesis).

## Artifacts / status
- Worktree `feat/console-sidebar-upgrade`; parent `e696630`, submodule `82e009b` (re-pinned). **Not pushed/merged.**
- 0 new runtime deps. Code summary: `construction/console-sidebar-upgrade/code/code-summary.md`.
- **Remaining before merge**: tsgo (submodule), R3/R4 live, push + parent re-pin push, F5 coordination (share the single
  width signal; F6 deliberately omits F5-owned sidebar default-on / rebrand).

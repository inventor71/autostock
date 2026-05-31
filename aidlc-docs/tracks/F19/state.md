# Track F19 — F9 follow-up: opencode permission keys for the structured order tools

> Per-track state. Single writer = this track's worktree session. Submodule (fork) change —
> branch inside the submodule, push fork, bump parent gitlink at merge.

## Track Info
- **Track ID**: F19
- **Title**: Add the 6 `autostock_*` structured-tool permission keys to the fork opencode config
- **Type**: fix (F9 follow-up #1; submodule/fork config)
- **Status**: merged (submodule feat/F19 → fork main `bc82b71`, pushed; parent gitlink bumped, feat/F19 → main `a1851e0`; 2026-05-31)
- **Branch**: feat/F19 (parent) + feat/F19 (submodule operator-console/cli)
- **Worktree**: .claude/worktrees/F19
- **Submodule branch**: feat/F19 → fork `main` (push to inventor71/autostock-cli, like F8/F13)
- **Base commit**: 2f13a7a (parent main); submodule base aa984da (fork main)
- **Start Date**: 2026-05-31

## Problem
F9 merged the structured Alpaca order tools (`place_stock_order` etc.) into the MCP server
(`operator-console/src/mcp-server.ts`, parent repo), but the **fork opencode config**
(`operator-console/cli/opencode.json` + `.opencode/opencode.jsonc`) defaults `"*": "deny"` and only
allows `autostock_steer` / `autostock_steer_read`. So opencode **denies/hides the new tools** → the
console AI never sees `place_stock_order` and falls back to the slash `/buy` (market-only) — observed
live: console said "지정가 매수 직접 불가, /buy만". F9's "no submodule change" scope missed this.
See [[f9-gated-alpaca-orders]] (follow-up #1), [[f4-steering-runtime-wiring]].

## Fix
Add to the `permission` block in BOTH fork config files:
`autostock_place_stock_order`, `autostock_cancel_order_by_id`, `autostock_cancel_all_orders`,
`autostock_replace_order_by_id`, `autostock_close_position`, `autostock_close_all_positions` = `"ask"`.

## Stage Progress (minimal depth)
- [x] Workspace Detection — brownfield; config fix
- [x] Requirements — explicit (the deny gap above); design/units SKIP
- [ ] Construction — edit both fork config files (submodule), commit on submodule feat/F19
- [ ] Build & Test — JSON/JSONC valid; (perm-gated tool availability proven live in F9 attach verify)
- [ ] Merge — submodule feat/F19 → fork main + push; bump parent gitlink; parent feat/F19 → main.
      Then operator: `git submodule update` in main + **restart the console** so opencode re-reads
      config and the MCP re-registers → `place_stock_order` becomes available (ask-gated).

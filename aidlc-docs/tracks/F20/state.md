# Track F20 — Alpaca-shaped read tools (arbitrary-symbol quotes / order lookup)

> Per-track state. Single writer = this track's worktree session. **OPENED only** (no
> construction yet). See [[f9-gated-alpaca-orders]] (F9 §5 scoped reads OUT).

## Track Info
- **Track ID**: F20
- **Title**: Alpaca-shaped read/market-data tools for the operator console
- **Type**: feature (F9 follow-up — read side)
- **Status**: active (opened; requirements/design TBD)
- **Branch**: feat/F20 (worktree at construction)
- **Worktree**: (TBD)
- **Submodule branch**: likely yes — new read tools need opencode permission keys in the fork
  config (`operator-console/cli/{opencode.json,.opencode/opencode.jsonc}`), same as F19.
- **Base commit**: 79df84a (main)
- **Start Date**: 2026-05-31

## Problem (observed live)
The console can now PLACE structured orders (F9), but **reads were left on the old `steer_read`
slash/snapshot path** (F9 requirements §5 deferred them). So an operator asking "MSFT 현재가?" gets
nothing — `/book` only shows held/resting-order symbols, with no arbitrary-symbol quote. The AI has
no Alpaca-shaped read tool to call.

## Rough scope (to refine in Requirements)
- Add Alpaca-shaped READ MCP tools (read-only, no order authority): e.g. `get_stock_quote` /
  `get_latest_trade` / `get_stock_bars` / `get_orders` / `get_positions` for **arbitrary symbols**.
- Decide gating: reads are non-mutating → opencode permission `allow` (like `steer_read`), NOT `ask`.
- Reuse the broker/data-provider read path (`market.py` / `AlpacaBroker.get_latest_prices` etc.);
  advisor-only invariant unaffected (reads only).
- Fork opencode config: add the new read-tool permission keys (`allow`).
- Cross-language contract (NFR-3) if the tools file-drop; but reads likely answer in-process
  (snapshot/market) without a daemon round-trip — decide in design.

## Open questions (for Requirements)
- Which Alpaca read tools to mirror (quotes only, or full read surface)?
- In-process market-data fetch vs daemon snapshot round-trip?
- Rate/quota + market-closed behavior (last trade vs quote).

## Stage Progress
- [x] Opened (registry + this record)
- [ ] Requirements / design / construction — NOT started

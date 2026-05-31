# Track F21 — place_stock_order arg robustness (fail-fast + omit-optional guidance)

> Per-track state. Single writer = this track's worktree session. **OPENED only** (no
> construction yet). See [[f9-gated-alpaca-orders]].

## Track Info
- **Track ID**: F21
- **Title**: Harden `place_stock_order` against junk/placeholder optional args + validate before queue
- **Type**: fix (F9 follow-up — robustness)
- **Status**: active (opened; requirements/design TBD)
- **Branch**: feat/F21 (worktree at construction)
- **Worktree**: (TBD)
- **Submodule branch**: — (parent repo: `src/agent/steering/commands.py` + `operator-console/src/mcp-server.ts`)
- **Base commit**: 79df84a (main)
- **Start Date**: 2026-05-31

## Problem (observed live)
A weak console model (GPT-5.5 Fast) filled OPTIONAL fields with placeholder `0.01` and set BOTH
qty and notional:
`place_stock_order[symbol=AAPL, side=buy, qty=1, notional=0.01, limit_price=300, stop_price=0.01,
trail_price=0.01, trail_percent=0.01, take_profit=0.01, stop_loss=0.01, ...]`. Because the market
was closed, `_v_place_order` **queued it BEFORE structural validation** (`_order_from_place_args`
runs only after the market-open check), so it reported "주문 접수" — but at next open the drain
re-runs it and the gate **rejects** (qty+notional both set → "specify either qty or notional";
trail_* on a non-trailing order → Order validator; `take_profit 0.01 ≤ entry` → price-sanity). Net:
a misleading "accepted" for an order that will silently fail at open.

## Rough scope (to refine in Requirements)
1. **Fail-fast: validate structure BEFORE queuing.** Move `_order_from_place_args` + Order
   construction (FR-7 notional/qty exclusivity, trail/class validity, price-sanity that doesn't
   need live price) ahead of the market-open/`queue_offhours` branch in `_v_place_order`, so a
   malformed order is rejected immediately with a reason — never queued as junk.
2. **Discourage placeholder optionals.** Tighten the zod tool description + field descriptions in
   `mcp-server.ts` ("omit optional fields entirely if unused; never pass 0/placeholder"). Consider
   treating `notional`/`trail_*`/`take_profit`/`stop_loss` ≤ 0 (or a tiny epsilon) as unset, and/or
   rejecting an obviously-degenerate value, so a weak model can't smuggle junk past `.positive()`.
3. Make the queued-vs-accepted outcome wording honest (deferred ≠ validated-accepted).

## Open questions (for Requirements)
- Sanitize-to-None vs hard-reject on degenerate optionals (0.01 take_profit on a $300 stock)?
- How much price-sanity can run pre-queue (without a live price when market closed)?
- Should `qty`+`notional` both-set be a hard reject (current) or prefer one?

## Stage Progress
- [x] Opened (registry + this record)
- [ ] Requirements / design / construction — NOT started

# Track F20 — Alpaca-shaped read tools (arbitrary-symbol quotes / order lookup)

> Per-track state. Single writer = this track's worktree session. **OPENED only** (no
> construction yet). See [[f9-gated-alpaca-orders]] (F9 §5 scoped reads OUT).

## Track Info
- **Track ID**: F20
- **Title**: Alpaca-shaped read/market-data tools for the operator console
- **Type**: feature (F9 follow-up — read side)
- **Status**: active (inception: requirements complete, awaiting approval)
- **Branch**: feat/F20 (worktree at construction)
- **Worktree**: (TBD — create before Code Generation Part 2)
- **Submodule branch**: feat/F20 (permission keys in fork, same as F19 — Q6=A)
- **Base commit**: 79df84a (main)
- **Start Date**: 2026-05-31

## Architecture Decision (key)
**Q2=A: Console in-process TS calls Alpaca Data API directly.** No daemon round-trip, no new
FileDrop channel. MCP server (bun/TS) uses native `fetch` → Alpaca REST v2. Requires
`ALPACA_API_KEY` + `ALPACA_API_SECRET` env vars wired to MCP env (new — not yet wired).

## Scope (finalized — Q1=C→C-2, stock-only 실용 서브셋)
16 Alpaca MCP stock-only 읽기 도구 (Alpaca MCP 공식 이름·파라미터 1:1 매칭):
- Trading Read: `get_account_info`, `get_all_positions`, `get_open_position`, `get_portfolio_history`
- Assets/Calendar: `get_asset`, `get_all_assets`, `get_calendar`, `get_market_clock`
- Stock Market Data: `get_stock_bars`, `get_stock_latest_bar`, `get_stock_latest_quote`, `get_stock_latest_trade`, `get_stock_quote`, `get_stock_snapshot`, `get_stock_trades`
- Orders: `get_orders`
All `allow`-gated (Q4=A). Crypto/Options/Watchlists/Corporate Actions excluded.
Full details: `requirements/requirements.md`.

## Extension Configuration
| Extension | Enabled | Decided At |
|-----------|---------|------------|
| Security Baseline | Yes | Requirements Analysis (2026-05-31) |
| Property-Based Testing | Yes | Requirements Analysis (2026-05-31) |

## Stage Progress
- [x] Opened (registry + this record)
- [x] Requirements Analysis (Standard) — approved. Q1=C→C-2 stock-only.
- [x] User Stories — SKIP (내부 도구, 사용자 페르소나 불필요)
- [x] Workflow Planning — approved
- [x] Application Design (Standard) — approved. Q1=B (fail-fast), Q2=A (markdown table), Q3=A (comma-sep string).
  Artifacts: `application-design/{components,component-methods,services,component-dependency,application-design}.md`
- [x] Units Planning — SKIP (단일 유닛)
- [x] Units Generation — SKIP (분해 불필요)
- [x] Functional Design (Minimal) — 생성 완료. No questions needed (simple HTTP client + formatter).
  Artifacts: `construction/functional-design/{business-logic-model,business-rules,domain-entities}.md`
  PBT-01: 6개 property 식별 (P1-P6, fast-check).
- [x] Critic review — 8 findings. Applied: H1 (timeout), H2 (fail-fast rationale corrected), M1 (steer_read data trust hierarchy), M2 (ALPACA_PAPER env). LOW issues noted, no action.
  Design docs updated: +`REQUEST_TIMEOUT_MS`, +`ALPACA_PAPER`, +steer_read vs F20 guidance table (services.md), +FR-9.
- [x] Code Generation (Part 1 — planning) ✅
- [x] Code Generation (Part 2 — code + tests + config) ✅ — 5 files modified/created, 24 tests pass, typecheck clean
  - NEW: `operator-console/src/alpaca-data.ts` (AlpacaDataClient, 16 methods, TS interfaces, formatters)
  - MODIFY: `operator-console/src/mcp-server.ts` (import + 16 registerTool, steer_read desc updated)
  - NEW: `operator-console/test/alpaca-data.test.ts` (24 tests, PBT P1-P6)
  - MODIFY: `operator-console/cli/{opencode.json,.opencode/opencode.jsonc}` (16 perm keys + 3 env vars)
  - MODIFY: `docker-compose.verify.yml` (ALPACA_KEY/SECRET/PAPER)
  - MODIFY: `scripts/worktree-setup.sh` (Alpaca 키 언급)
- [x] Build and Test ✅ — summary: 92 tests pass (24 new + 68 existing), typecheck 19 packages pass, P1-P6 verified, 5/15 security rules compliant, no regressions

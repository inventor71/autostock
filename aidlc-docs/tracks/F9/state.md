# Track F9 — Alpaca-format Console Orders (limit/stop/TIF) through Risk/Broker gate

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F9
- **Title**: Alpaca-format console orders (limit/stop/stop-limit/TIF/notional) still gated by RiskManager→Broker
- **Type**: feature
- **Status**: merged (→ main `8948e24`, no-ff; base `e8d99a6`, 2026-05-31)
- **Branch**: feat/F9 (worktree-setup.sh convention: feat/<track>)
- **Worktree**: .claude/worktrees/F9
- **Submodule branch**: N/A — **CORRECTED 2026-05-31**: `operator-console/src/*.ts` (mcp-server/
  parser/schema/steer-handler) + `test/` + `contract/` are tracked by the **PARENT repo**, not the
  submodule. Submodule = `operator-console/cli` (opencode fork) is NOT touched by F9 (tools live in
  src/ + opencode.json config). Use `worktree-setup.sh F9 --ts --py` (--ts only to get bun/tsgo for
  typechecking parent-repo TS); commit NO submodule gitlink change.
- **Base commit**: a0b882d (main @ track creation)
- **Start Date**: 2026-05-31

## Extension Configuration
- **Security Baseline**: **Enabled** (Q-sec=A; all SECURITY rules blocking). Applicable here:
  SECURITY-11 (order/auth authority isolation — the new structured mutating tools must stay
  operator-console-only; advisor agents must not reach them), SECURITY-03 (operator token NEVER
  logged/echoed in tool results or events), SECURITY-15 (fail-closed: missing token / invalid
  args / risk-reject → no order). SECURITY-13 (safe-deserialize structured args). Others N/A
  (no web app, DB, IaC, user auth).
- **Property-Based Testing**: **Partial** (Q-pbt=B). Hypothesis. Applied to pure functions:
  qty↔notional conversion, risk-budget clamp, protection-level resolution, price-sanity checks,
  and structured (de)serialization round-trips (TS↔pydantic contract). Other rules advisory.

## Scope (redesigned 2026-05-31 after user clarification)
**Corrected architecture understanding:** the operator does NOT type slash commands — they speak
NL to the opencode operator-console AI, which today calls the steering MCP tool `steer({command:
"/buy AAPL 1sh"})` with a **slash-command STRING**; `steer-handler.ts`→`parser.ts` parses that
string (market-only grammar) into a `SteeringCommand`, file-drops it, and the daemon's
`build_human_buy` (market-only) runs it through RiskManager→Broker. The slash grammar's poverty IS
the limitation.

**Goal (new):** change the gate **contract** from a parsed slash STRING to **structured
Alpaca-MCP-shaped tool calls**. Add Alpaca-shaped structured tools (e.g. `place_stock_order` with
symbol/side/qty|notional/order_type/limit_price/stop_price/trail_*/time_in_force/order_class/
take_profit/stop_loss, plus cancel/replace/close) to the operator-console MCP server. Flow becomes:
**NL (or slash shorthand) → opencode AI → structured Alpaca-shaped MCP tool → (opencode `ask`
human-confirm) → structured SteeringCommand + token + file-drop → daemon RiskManager/Broker gate →
order(s) / reject.** Slash commands are **demoted to an AI-understood shorthand** (still usable
conversationally + for non-order lifecycle verbs), NOT the gate contract. advisor-only
research/intraday/PM agents (decisions.jsonl path) are UNTOUCHED.

Touches: `operator-console/src/mcp-server.ts` + `steer-handler.ts` + `schema.ts` (+ `parser.ts`
demoted, submodule), `src/agent/steering/records.py` (richer SteeringCommand args), `commands.py`
(replace `build_human_buy`/`_v_buy`/`_v_sell` with a structured order handler), `src/risk/manager.py`
(receive/validate a fully-specified Alpaca-shaped order), possibly `src/core/models.py` (Order:
trail/notional/extended_hours), `src/execution/brokers/alpaca_broker.py` (TIF/trailing/notional),
and the cross-language contract (contract.test.ts ↔ test_steering_contract.py).
Related: [[risk-execution-redesign]], [[console-native-launcher]], [[f4-steering-runtime-wiring]],
[[feedback-ui-concretization]].

## Stage Progress
- [x] Workspace Detection — Brownfield; RE artifacts exist (aidlc-docs/inception/reverse-engineering/)
- [x] Requirements Analysis — Standard/Comprehensive depth; v3 answered (Q1=A,Q2=A,Q3=A,Q4=B,Q5=A,
      Q6=A,sec=A,pbt=B); no blocking contradiction; requirements.md authored — **APPROVED 2026-05-31**
- [x] Workflow Planning — execution-plan.md authored + critic-revised (risk→High) — **APPROVED 2026-05-31**
- [ ] User Stories — **SKIP** (operator/AI-facing tool surface; no new personas; covered by requirements)
- [x] Application Design — answers locked (Q1-5=A); 5 artifacts authored — **APPROVED 2026-05-31**
- [x] Units Generation — **CONFIRMED** — 3 units, build bottom-up:
      U-RISK (risk gate + Order model + AlpacaBroker, py) → U-DAEMON (records+commands+py contract, py) →
      U-CONSOLE (mcp-server+schema+handler, delete parser.ts, +ts contract, TS submodule)
- [ ] Functional Design (per-unit) — **EXECUTE** (Order/SteeringCommand models, RiskManager reception logic, replace reconciliation)
- [ ] NFR Requirements — **SKIP** (NFR-1..5 already enumerated in requirements.md; no new tech-stack selection)
- [ ] NFR Design — **SKIP** (Security baseline is a blocking extension enforced inline at every stage;
      isolation/zod-boundary/fail-closed/token-handling designed within Application + Functional Design)
- [ ] Infrastructure Design — **SKIP** (no cloud/IaC; existing local daemon + file-drop channel)
- [x] Construction (per-unit Code Generation) — **DONE** in worktree `.claude/worktrees/F9` (branch feat/F9):
      U-RISK 4db4771, U-DAEMON 9eaf263, U-CONSOLE baf3cd2
- [~] Build & Test — **GREEN (automated)**: Python 414 passed (+25 U-RISK incl. Hypothesis PBT,
      +13 U-DAEMON), golden contract 4 passed, console 64 passed (+per-verb args + structured path).
      Live TEST-account smoke = **pending user go-ahead** (places orders → outward-facing).

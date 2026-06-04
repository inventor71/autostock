# Track R0 — Genesis structural refactor (archived pre-partition history)

> The project's first AI-DLC work (predates F-numbering): a brownfield structural review +
> behavior-preserving refactor sequence S-5 → S-3 → S-1+S-2 → S-4 (units U1–U7). Migrated
> 2026-06-04 from the root `aidlc-state.md` (root = Track Registry only). Reverse-engineering
> artifacts for this work currently live under `tracks/M1/inception/reverse-engineering/`
> (`architecture.md`, `code-quality-assessment.md`). Registry row R0 is authoritative for status.

## Track Info
- **Track ID**: R0
- **Title**: Genesis structural refactor (S-5/S-3/S-1+S-2/S-4 → U1–U7)
- **Type**: refactor (brownfield, behavior-preserving)
- **Status**: merged (complete 2026-05-28; tests 155 → 179)
- **Start Date**: 2026-05-28

## Project Information
- **Project Type**: Brownfield
- **Start Date**: 2026-05-28T00:00:00Z
- **Current Stage**: INCEPTION - Reverse Engineering (awaiting approval)
- **Workflow Goal**: Review the existing project and identify structural improvements that must be made.

## Workspace State
- **Existing Code**: Yes
- **Programming Languages**: Python 3.11+ (single language)
- **Build System**: Hatchling / pyproject.toml
- **Project Structure**: Modular monolith (`src/` layered packages)
- **Reverse Engineering Needed**: Yes (no prior artifacts)
- **Workspace Root**: /home/jihoonpark/Project/autostock

## Code Location Rules
- **Application Code**: Workspace root (NEVER in aidlc-docs/)
- **Documentation**: aidlc-docs/ only
- **Structure patterns**: See code-generation.md Critical Rules

## Extension Configuration
- **Security Baseline**: Enabled (enforce, all rules blocking). Applicable to this
  refactoring: SECURITY-03 (no secrets in logs), SECURITY-11 (risk/auth logic isolated),
  SECURITY-15 (explicit error handling, fail-closed). Most others N/A (no web app, DB,
  IaC, or user auth). SECURITY-10/12 (dep pinning, hardcoded creds) noted as pre-existing,
  not introduced by these units.
- **Property-Based Testing**: Enabled — **Partial mode**. Enforced rules: PBT-02, PBT-03,
  PBT-07, PBT-08, PBT-09. Applied to pure functions only (e.g. PositionSizer.calculate_shares,
  RiskManager._resolve_stop / ratchet_stop). Framework: Hypothesis (PBT-09). Other rules advisory.

## Construction Scope (user-approved 2026-05-28)
Sequential refactoring units, in user-specified order. Remaining findings (Q-*, H-*) deferred.

| Unit | Finding | Goal |
|------|---------|------|
| **U1** | S-5 | De-stale docs/comments: update DESIGN.md (agent path, §9), strip "Phase N" framing, fix README (modes/test count/features), remove dead `research_prompt()` if unused |
| **U2** | S-3 | Remove `config.config` reach-ins inside `src/`; inject needed values via constructor/params |
| **U3** | S-1 + S-2 | Unify the 3 risk-exit implementations into one; make RiskManager bracket-mode a construction-time choice (drop runtime mutation) |
| **U4** | S-4 | Add explicit broker capabilities (trade-ledger / market-clock port) to replace `getattr(_client)` duck-typing; type `portfolio_provider` |

## Stage Progress
- [x] Workspace Detection — Completed 2026-05-28 (Brownfield)
- [x] Reverse Engineering — Approved 2026-05-28
  - **Artifacts Location**: aidlc-docs/inception/reverse-engineering/
- [~] Requirements Analysis — Minimal depth; extension opt-ins being confirmed
- [ ] User Stories — SKIPPED (pure internal refactoring, no user-facing change)
- [ ] Workflow Planning — Sequence fixed by user (U1→U2→U3→U4)
- [~] Construction (per-unit Code Generation) — in progress
  - [x] **U1 (S-5)** — docs/comments de-staled. Completed 2026-05-28.
    - Removed all 6 "Phase N" scaffolding comments from src/; deleted dead `research_prompt()`.
    - Fixed orchestrator docstring (executor does execution, not "Phase 3").
    - README: added LLM strategy + agent mode to feature table & structure, added agent usage
      section, fixed stale backtest example (`Symbol: AAPL`→`Universe`), dropped "42개" count.
    - DESIGN.md: §1/§3 note the agent path, new §5.8 (agent subsystem), §9 refreshed + linked to
      the structural review. Tests 158 green; no logic changed.
  - [x] **U2 (S-3)** — config injection. Completed 2026-05-28.
    - Removed all library-code `get_settings()` reach-ins (5 sites). Kept only the two CLI
      entry points (`equity_log.main()`, `agent/tools/__main__.py`) as composition roots.
    - orchestrator/executor: `universe` now keyword-only required (no global fallback).
    - modes/agent: ledger config (`experiment_start`, `min_trade_notional`) injected via ctor.
    - llm_strategy: reads provider config + `api_key` from params (literal LLMConfig defaults);
      auto_improver: `provider`/`api_key` injected.
    - main.py wires it: `_resolve_api_key()`/`_llm_params()` helpers, `create_strategies(…, settings)`
      injects llm config (strategies.yaml params override), agent ledger config passed to AgentTradingMode.
    - Added 7 tests (LLMStrategy config injection + main injection helpers) — llm/ had no coverage.
    - Tests 165 green; behavior preserved (note: U4 will further fix the `getattr(_client)` leak in modes/agent).
  - 7db787c (user's concurrent commit, "research timeout") reconciled — no conflict with U1/U2.
  - [x] **U3 (S-1+S-2)** — unify risk-exit + RiskManager mode. Completed 2026-05-28 (commit 360bb4c).
    - Added `src/risk/exits.py::run_polled_exits()` as the single implementation; three sites
      (`TradingEngine._check_risk_exits`, `_check_symbol_risk_exit`, `DecisionExecutor.run_risk_exits`)
      delegate to it.
    - Removed `DecisionExecutor.__init__` runtime mutation of `risk_manager.use_bracket_orders`;
      now validates the contract (raises ValueError if not bracket-mode — fail-closed, SECURITY-15).
    - Test helper + 2 run_risk_exits tests updated to construct `RiskManager(use_bracket_orders=True)`.
    - Added Hypothesis to dev deps (PBT-09); new `tests/test_exits.py`: 6 example tests + 1
      Hypothesis property (PBT-03 invariant: protected symbols never yield exit orders) + 2
      fail-closed contract tests. Tests 174 green.
    - Note: `src/backtest/engine.py` has a similar 4th call site (different price-refresh path);
      left as-is for this unit, could fold in later.
  - [x] **U4 (S-4)** — broker port for the trade ledger + honest portfolio_provider type.
    Completed 2026-05-28 (commit 7aa7d6e).
    - Added `BaseBroker.record_trade_ledger(path, *, since, min_notional)` with no-op default.
      `AlpacaBroker` overrides it (delegates to `record_trades(self._client, ...)`).
      `modes/agent.py:_eod` now calls it unconditionally — leak `getattr(broker, "_client", None)` gone.
    - `AgentTradingLoop.portfolio_provider` typed `Callable[[], PortfolioState] | None`;
      `held_symbols()` drops the `getattr(portfolio, "positions", None)` duck-typing.
    - 2 new tests in `test_execution.py::TestTradeLedgerPort`: default no-op on simulated;
      AlpacaBroker delegation (monkeypatch `record_trades`, assert forwarded args). 176 tests green.

  - [x] **U5 (B-1+B-2)** — backtest fidelity. Completed 2026-05-28 (commit 9384b3c).
    - B-1: metrics now from `match_round_trips` (moved to `src/core/trades.py`, shared with the
      live ledger) — `total_trades`/`win_rate` count closed round-trips, not every fill (was ~2x / half).
    - B-2: backtest feeds bar high/low and arms resting OCO protection on entry, so stops/takes
      trigger intra-bar at the trigger price (mirrors live), not close-only. Also resolves the
      backtest's inline polled-exit block (the 4th risk-exit duplication site).
    - `SimulatedBroker.set_current_price` now returns triggered fills; `BacktestResult.trades` populated.
    - 2 new fidelity tests. 178 green.
  - [x] **U6 (B-3)** — sell sizing. Completed 2026-05-28 (commit 816f298).
    - `RiskManager._handle_sell`: dropped `int()` truncation + min-1-share floor; full exit sells exact
      `position.qty` (fractional-safe), sell_pct→0 returns no order. Corrected 2 bug-encoding tests + 1 new. 179 green.

  - [x] **U7 (M-1)** — removed dead `PortfolioState.total_value` duplicate. Completed 2026-05-28.
    - `equity` is now the single source of account value (broker-authoritative); added a model
      comment warning against re-adding a divergent recompute. `test_core.py` assertion retargeted
      to `equity`. DESIGN §4/§9 updated. 179 green.

## Completed Sequence Summary
**Approved structural sequence** S-5 → S-3 → S-1+S-2 → S-4: all complete.
**Closer-inspection bugs** (found on re-review) B-1, B-2, B-3: all fixed.
**Maintainability** M-1: fixed.
Tests 155 → 179. Working tree clean.
**Remaining (deferred)**: Q-1 (WorkspaceStore), Q-3 (`get_status` mode), Q-4 (test coverage:
TradingEngine/LLM/providers/AgentSession), Q-5 (lazy imports), H-1 (short positions),
H-2 (dev-env: single venv + ruff), H-3 (repo hygiene). See `code-quality-assessment.md`.

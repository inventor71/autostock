# AI-DLC State Tracking

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

## New Feature Track: Dynamic Intraday Pattern Detection (F1)
- **Started**: 2026-05-28. **Stage**: INCEPTION → Requirements Analysis (intent/feasibility), minimal.
- **Requirements doc**: `aidlc-docs/inception/requirements/intraday-pattern-feature.md`
- **Feasibility verdict**: observation valid; naive "LLM predicts shifting patterns" risky
  (non-stationarity → ~20–60 sessions/regime, not backtestable, narrative-overfitting risk).
  Reframed to "falsifiable hypothesis lifecycle + honest out-of-sample scoring" on the existing
  agent/journal/EOD-review architecture. Phased P0→P3.
- **User decision**: build **P0 only first (exploratory)** — answer "do these patterns
  statistically exist & persist?" with real data, then re-decide P1+.
- **P0 plan — DONE 2026-05-28** (15 new tests; suite 179 → 194 green):
  - [x] `src/data/intraday_features.py` — pure per-session features + `FEATURE_COLUMNS`
  - [x] `src/data/intraday_store.py` — CSV-backed `IntradayFeatureStore` (`data/intraday/`), idempotent on (date,symbol)
  - [x] `src/data/intraday_collector.py` — `sessionize`/`features_for_symbol`/`collect` + CLI (`backfill`/`today`)
  - [x] `src/data/intraday_analysis.py` — `Hypothesis` registry, conditional edge (n/hit_rate/excess/t-stat),
        rolling-window stability, md/JSON report + CLI
  - [x] `tests/test_intraday.py` — features (example + Hypothesis invariants), store round-trip/idempotency,
        collector sessionize/prev-close-chaining/failure-tolerance, analysis injected-pattern vs flat
  - **Live-validated**: real yfinance backfill (AAPL, 14 sessions) → report rendered; rolling view already
    shows a candidate pattern flipping sign across windows (non-stationarity made visible — the intended signal).
  - Decisions: CSV (no new dep; pyarrow absent, pandas 3.0 present, swappable backend), MINUTE_5 bars via
    existing provider, universe from `config/settings.yaml`; no LLM/web/trading in P0.
  - **P0+ (2026-05-28): Alpaca + date-range backfill added** for deep multi-year history. `collect()` takes
    `start`/`end` (limit dropped in range mode); CLI `backfill --provider {yfinance,alpaca} --start --end`.
    2 new collector tests (range vs limit call routing); suite 194 → 196 green. Live-validated: Alpaca pulled
    107,633 AAPL 5m bars (2024-01→2026-05) → 633 sessions; report over 647 sessions shows only
    `gap_down_reversion` flickering (t≈2.8 but n=12 with one window flipping negative) — the small-sample /
    non-stationarity reality, and the case for a full-universe backfill (×~105 → ~100× the conditional n).
  - **Next (user re-decides):** run a full-universe Alpaca backfill, read the stability report, then decide whether
    P1 (hypothesis lifecycle in journal + EOD out-of-sample scoring) is worth building.

## New Feature Track: Human-Steering Console for Agent Mode (F2)
- **Started**: 2026-05-28. **Stage**: INCEPTION → Requirements Analysis (comprehensive-leaning), awaiting answers at the gate.
- **Goal**: A console on `main.py --mode agent` for human-in-the-loop steering in natural language
  (e.g. "sell AAPL"). Must (1) carry out the intent, (2) durably log the intervention, and (3) keep the
  running agent consistent (the agent becomes aware of the human change so its journal/theses/protection
  don't drift). Headline value: correcting an AI mistake quickly in plain language.
- **Integration surface mapped** (read 2026-05-28): `main.run_agent` → `modes/agent.AgentTradingMode`
  (scheduler + `while True` loop) → `agent/orchestrator.AgentTradingLoop` (LLM turns, journal writes) +
  `agent/executor.DecisionExecutor` (the ONLY order-placing path: journal `decisions.jsonl` → RiskManager
  bracket → Broker, cursor-idempotent) over the file-based `agent/journal.Journal` (workspace/).
- **Questions doc**: `aidlc-docs/inception/requirements/human-steering-console-questions.md` (answered).
  **Requirements doc**: `aidlc-docs/inception/requirements/human-steering-console.md`.
- **Confirmed decisions (2026-05-28):** Q1=B in-process REPL thread; Q2=C hybrid (structured verbs +
  NL notes); Q3=B echo+confirm for trades; Q4=C trades+lifecycle+context steering; Q5=B passive channel +
  immediate reconcile turn; Q6=A same RiskManager→Broker gate; Q7=A structured logging now (learning deferred);
  Q8=A new worktree+branch; Q9=A security enforced; Q10=B PBT partial.
- **Core NFR (NFR-1):** single serialized command path (lock/queue) shared by console + scheduler +
  reconcile turn — avoids broker/cursor/CLI-session races. Same queue enables a future file-drop front-end
  (headless/detached) cheaply. **Open assumption:** trader run attached (foreground/tmux), not detached —
  to confirm at approval (else 1st front-end becomes file-drop).
- **Extension Configuration (F2):** Security Baseline = Enabled (enforce; applicable SECURITY-03/11/13/15,
  others N/A — local CLI). Property-Based Testing = Partial (PBT-02/03/07/08/09; Hypothesis; parser +
  HumanDirective record round-trip). Consistent with the project-wide config above.
- **Execution plan**: `aidlc-docs/inception/plans/execution-plan.md` (Workflow Planning). Risk: Medium–High
  (touches live order path + adds concurrency to the running daemon); rollback easy (worktree/branch).
- **Single unit**: `human-steering-console`. Internal build sequence: record/channel/`source` tag → parser/log →
  serialized command path + lifecycle state → human-trade route via executor → reconcile turn + prompts → REPL + wiring.
- **Stage Progress (F2)**:
  - [x] Workspace Detection — reused (brownfield, existing project).
  - [x] Reverse Engineering — reused (artifacts already exist).
  - [x] Requirements Analysis — complete 2026-05-28 (requirements.md; extensions recorded). **Approved.**
  - [x] User Stories — **SKIP** (single-operator tool; workflows captured as FRs; user chose Approve & Continue).
  - [x] Workflow Planning — complete 2026-05-28 (execution-plan.md). **Approved** ("승인할게. 진행하자").
  - [x] Application Design — **SKIP** (folded into Functional Design; single small component set).
  - [x] Units Generation — **SKIP** (single cohesive unit).
  - [x] Functional Design — **COMPLETE** 2026-05-29 (awaiting approval). Q1–Q10 + clarification CQ1–CQ6 answered.
        Artifacts in `aidlc-docs/construction/human-steering-console/functional-design/`: domain-entities.md,
        business-logic-model.md, business-rules.md, frontend-components.md.
        **Key locked decisions:** all `/command` slash grammar; `/buy SYM <N$|Nsh>`, `/sell SYM <N%|Nsh|N$>`
        (reject bad/missing unit); `[y/N]` confirm, `CONFIRM` keyword for `/flatten all`+`/kill`; loguru stdout
        off→file + console as a monitor.sh pane (console==daemon, in-process REPL); async reconcile on trades+directives.
        **Human-approval gate (Q8, scope addition → requirements §8.1 FR-8):** human trade → symbol human-locked →
        agent BUY/SELL on it parked as PendingApproval (`/pending`,`/approve|/reject`); approve→unlock, reject→count++,
        2 rejects→denied-for-day; `/unlock` manual, ET-date auto-clear; protective orders + risk-exits exempt;
        approve/reject outcome fed back to agent. RunState(pause/halt) not persisted (restart→running, Q9=A).
        **Test env (CQ6=A):** separate Alpaca paper account (already created) + isolated workspace for manual smoke.
        **Worktree deferred to Code Generation entry** (design = docs only).
  - [→] NFR Requirements — NEXT (minimal).
  - [ ] NFR Requirements — **EXECUTE (minimal)** (tech stack: no new runtime deps, stdlib threading/cmd, Hypothesis).
  - [ ] NFR Design — **EXECUTE** (single serialized command path + turn-lock; security placement; fault isolation).
  - [ ] Infrastructure Design — **SKIP** (local CLI, no infra change).
  - [ ] Code Generation — **EXECUTE**. [ ] Build and Test — **EXECUTE** (no-regression of 196 tests + new PBT/concurrency).

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
  - [x] Functional Design committed 2026-05-29 (`bfbb8a9`, with inception docs + Korean question-file prompt rule).
  - [x] NFR Requirements — **COMPLETE (minimal)** 2026-05-29 (awaiting approval). Artifacts in
        `aidlc-docs/construction/human-steering-console/nfr-requirements/`: nfr-requirements.md, tech-stack-decisions.md.
        **Conclusion: zero new runtime dependencies** (stdlib threading/input-loop + hand-rolled slash parser; pydantic/
        loguru/APScheduler/claude CLI/Hypothesis(dev) reused). No new question round (decisions already settled by
        Q9/Q10 + "no new runtime deps" + NFR-1). Deferred to NFR Design: serialization primitive (Lock vs queue worker)
        + scheduler single-worker config.
  - [x] NFR Requirements — **COMPLETE** 2026-05-29 (awaiting approval). Console UI stack reconsidered (CQ-NFR1=B,
        CQ-NFR2=A): **adopt `prompt_toolkit` + `rich`** (2 new runtime deps, pinned → SECURITY-10) for a seamless line
        REPL in the monitor.sh pane (autocomplete/history/bottom-toolbar/`patch_stdout`/rich tables). textual full TUI
        NOT in v1 (north-star only). Driver beyond aesthetics: bare `input()` corrupts the in-progress line when the
        async approval notice (CQ2=A) prints — `patch_stdout` fixes exactly this. Updated tech-stack-decisions.md,
        nfr-requirements.md, frontend-components.md, requirements §NFR-3. Deferred to NFR Design: serialization
        primitive (Lock vs queue), scheduler single-worker, prompt_toolkit event-loop-in-thread × patch_stdout × the
        serialized path.
  - [x] NFR Design — **COMPLETE** 2026-05-29 (awaiting approval). Artifacts in
        `aidlc-docs/construction/human-steering-console/nfr-design/`: nfr-design-patterns.md, logical-components.md.
        **Core concurrency decision:** two independent serialization axes — (1) a single **CommandWorker** thread is
        the ONLY thing that touches broker/executor/cursor (console mutations + approvals + `/cancel`/`/stop` +
        scheduler executor-phase + reads all enqueued → broker/cursor races structurally impossible), and (2) a
        **turn_lock** serializes `AgentSession` (scheduled turns + reconcile). Split so a long LLM turn (holds turn_lock,
        not broker) never blocks an emergency `/kill`/`/flatten`. SteeringState(state_lock) holds RunState(in-mem)+
        HumanLock/Pending/Directive(persisted, ET-date)+InterventionLog(append-only)+broker snapshot cache. Human trades
        run via a direct `execute_decision` path (NOT in decisions.jsonl → cursor idempotency preserved); agent learns
        via reconcile+live state. Notifier → patch_stdout for async approval notices. prompt_toolkit loop on the main
        thread (TTY) else sleep-wait; quit→console-only, Ctrl-C→daemon. Security P4 (SECURITY-03/10/11/13/15) mapped.
  - [~] NFR Design — **REVISED after cross-review 2026-05-29** (11 findings vs actual code; all valid). Engineering
        fixes applied to docs: #1 emergency priority lane + honest worst-case bound (~6s in-flight op, not "instant");
        #2 lazy ET-date expiry + midnight sweep (daemon never restarts, session.py:119 live-ET); #3 id rehydrate
        (counter=max+1 on load); #4 idempotent PendingApproval parking + incremental cursor; #5 reconcile
        turn_lock.acquire(blocking=False) + explicit skip logging (BackgroundScheduler max_instances=1 coalesce);
        #6 confirm shows estimate, executor re-queries live + result shows actual (TOCTOU); #7 precise invariant
        (broker *mutations*+cursor single-thread; read-only is_market_open via cached snapshot) + rewire list;
        #8 torn-line guard (skip incomplete trailing line; cursor=complete lines), decisions.jsonl is cross-axis;
        #11 prompt_toolkit buffer-preservation = code-gen verification item. Policy forks resolved: **CQ-D1=A**
        (RunState ET-date persisted → same-day crash/manual restart restores pause/halt; next trading day auto-running;
        `run_state.json`), **CQ-D2=A** (lock on success only, BR-4.1 unchanged). Docs updated accordingly.
  - [x] NFR Design — **COMPLETE & APPROVED** 2026-05-29 ("답했어. 승인.").
  - [x] Infrastructure Design — **SKIP** (local CLI, no infra).
  - [~] Code Generation **Part 1 (plan)** — created 2026-05-29; only **1 new runtime dep** (`prompt_toolkit`).
        `aidlc-docs/construction/plans/human-steering-console-code-generation-plan.md`. Worktree NOT yet created (Part 2 first action).
  - **`/critic` adversarial review (isolated subagent) 2026-05-29 — 8 findings, all verified valid vs code.** Engineering
        fixes applied to design+plan docs: #1 invariant leak (agent `claude` subprocess holds an independent read-only
        `AlpacaBroker` via `tools account`, __main__.py:21-30 → restated invariant as daemon-internal mutation+cursor,
        not global single-broker-thread); #2 torn-line guard is NOT in current code (splitlines, journal.py:110) → marked
        "code-gen adds it" + cursor = complete physical lines (fix existing skip drift); #3 worst-case emergency bound
        ~6s→**~11s** (submit_order fill-poll ~5s + cancel_and_wait 6s, alpaca_broker.py:77-100); #4 scheduler has no
        explicit max_instances/coalesce (scheduler.py:13, relies on defaults) → set explicitly; #6 `/unlock`+sweep must
        resolve outstanding PendingApprovals + re-trade resets denied (BR-4.10/4.11, FR-8 qualified); #7 load-time
        ET-date check + cross-midnight restart test; #8 plan Step6 integration test for emergency-yield re-entry
        idempotency. Validated-as-sound: discretionary-vs-protective SELL gating (protective never uses Decision SELL).
        **Policy forks resolved:** **CQ-R1=A** (reconcile = bounded-blocking + priority over next scheduled turn;
        max-staleness = in-flight turn remainder) + **CQ-R2=A** (off-hours human trades → `pending_human_trades.jsonl`
        queue, drained by the market-open job; HumanLock still created off-hours). Docs updated (patterns P2, LC4,
        BR-6.2, BR-2.7, data-store table, plan Step5/9).
  - [x] **NFR Design — FINAL** 2026-05-29 (all critic findings + CQ-D1/D2 + CQ-R1/R2 incorporated).
  - [~] Code Generation **Part 1 (plan) — REVISED & ready, awaiting approval to enter Part 2.** On approval, Part 2's
        first action = create git worktree+branch (Q8=A), then implement Steps 1–11 there. No code/worktree yet.
  - [ ] NFR Requirements — **EXECUTE (minimal)** (tech stack: no new runtime deps, stdlib threading/cmd, Hypothesis).
  - [ ] NFR Design — **EXECUTE** (single serialized command path + turn-lock; security placement; fault isolation).
  - [ ] Infrastructure Design — **SKIP** (local CLI, no infra change).
  - [ ] Code Generation — **EXECUTE**. [ ] Build and Test — **EXECUTE** (no-regression of 196 tests + new PBT/concurrency).

## New Feature Track: Intraday Loop Redesign (F3)
- **Started**: 2026-05-29. **Stage**: INCEPTION → Requirements Analysis (Standard depth), awaiting answers at the gate.
- **Goal**: Redesign the agent's 15-min intraday loop so the LLM fires on *judgment-worthy state changes* rather than
  on every clock tick. Bundles 5 improvements (user: "5개 전부 묶은 재설계"): (A) Python deterministic pre-gate that
  wakes the LLM only on real events; (B) Python-assembled brief injected each waking turn (price/levels/distance/account/
  delta) to stop the agent re-deriving the book from scratch; (C) intraday news diff to revive the dead "thesis changed?"
  branch; (D) structured watch-triggers + Python-detected conditional ADJUST_STOP (advisor-only preserved); (E) effectively
  adaptive cadence via the gate; (F) no-op ticks logged as a one-line heartbeat with no LLM call.
- **Evidence (today's session, read via `scripts/agent_trace.py`)**: 13 intraday turns, only 1 produced a decision; the
  other 12 re-pull quote×5 and re-state the same table; `run_intraday()` passes no quotes (prompt price line always empty);
  intraday never uses account/news/scoreboard; META fill was inferred from a quote low crossing $630 (not confirmed via
  account → journal/broker desync risk); the catalyst branch is dead (news never pulled intraday).
- **Locked-architecture alignment**: [[llm-trader-redesign]] advisor-only (decisions.jsonl→RiskManager→Broker is the sole
  gate); [[risk-execution-redesign]] exchange resting OCO = always-on mechanical trigger, **LLM intraday turn = judgment/
  adjustment layer, must NOT carry the "did price hit my level" burden**. The current loop violates this; the redesign
  implements the stated intent. The agentic path is paper/live-only and NOT backtestable (per llm-trader-redesign #7), so
  no backtest-parity concern for this track.
- **Integration surface**: `prompts.intraday_prompt`, `orchestrator.run_intraday`, `modes/agent._intraday` (gate+cadence),
  `agent/review.outcome_lines` (brief-assembly pattern to reuse), `agent/tools/market.account|news`, journal (`workspace/`)
  for structured watch-triggers + heartbeat in `turns.jsonl`.
- **Extensions (F3)**: default to project-wide config (Security Baseline = Enabled; PBT = Partial/Hypothesis) — confirming via Q12.
- **Stage Progress (F3)**:
  - [x] Workspace Detection — reused (brownfield, existing project).
  - [x] Reverse Engineering — reused (artifacts already exist).
  - [x] Requirements Analysis — **COMPLETE** 2026-05-29 (awaiting approval). Q1–Q12 + integration CQ-A..CQ-D answered.
        Requirements doc: `aidlc-docs/inception/requirements/intraday-redesign.md`.
        **Key reframing (Q1=X):** do NOT gate-skip the LLM. Keep the 15-min scheduled intraday LLM turn (always runs) but make
        it cheap via a structured brief; ADD event-driven wake turns that fire out-of-band with priority. Value = correctness
        (account-truth fills + news diff) + responsiveness (immediate event wake) + quality (no re-derivation), NOT cost-cut
        (cost not a concern per user). **Locked answers:** watch.jsonl (Q3=A) for structured triggers; full brief w/ account
        snapshot + delta + news diff (Q4/Q5/Q6=A); wake conditions = new-fill / abnormal-move / watch-trigger / protective-
        reassess (Q2=A,C,D,E; NOT news→rides scheduled turn, NOT EOD-force→exists); conditional ADJUST_STOP = Python detects
        via watch.jsonl → wakes LLM to judge (Q9=A, advisor-only); single unit in worktree (Q10/Q11=A); extensions same (Q12=A).
        **F2 integration (CQ):** build F3 on top of F2 AFTER F2's initial implementation lands (CQ-A=A; design may precede);
        generalize F2 ReconcileWorker/TurnCoordinator as the shared single background-turn engine, add F3 trigger sources
        (CQ-B=A); account snapshot read from SteeringState.snapshot() cache, never broker off-thread (CQ-C=A, NFR-1); gate
        consults RunState — paused→hold LLM, entries_halted→suppress BUY-triggered wakes (CQ-D=A).
        **C-1/C-2 resolved (2026-05-29):** C-1 confirmed — no heartbeat in normal op (LLM always runs, no no-op tick), log
        suppression only while `/pause`d. C-2 — **skip-if-busy**: scheduled 15-min turn does a non-blocking turn_lock acquire
        and SKIPS if a wake turn is still running (overlaps the slot); back-to-back is fine (FR-3/NFR-1).
        **F2 status:** initial implementation COMPLETE (branch feat/human-steering-console @ f63fad2, 262 tests, not merged) →
        CQ-A=A "build F3 after F2 initial impl" precondition now satisfied; F3 construction can proceed on top once approved.
  - [x] Requirements Analysis — **APPROVED** 2026-05-29 ("Approve & Continue"); C-1/C-2 resolved.
  - [x] User Stories — **SKIP** (internal agent-behavior change; workflows captured as FR-1..7; consistent with F1/F2).
  - [x] Workflow Planning — **COMPLETE** 2026-05-29 (awaiting approval). Plan: `aidlc-docs/inception/plans/intraday-redesign-execution-plan.md`.
        Risk: **Medium** (touches live agent decision path but advisor-only — RiskManager→Broker gate unchanged; reuses F2 concurrency
        primitives, no new ones; worktree-isolated, easy rollback). **Stage determination:** Application Design SKIP (folded into
        Functional Design), Units Generation SKIP (single unit). CONSTRUCTION unit `intraday-redesign`: Functional Design EXECUTE,
        NFR Requirements EXECUTE (minimal — 0 new runtime deps), NFR Design EXECUTE (generalize ReconcileWorker + skip-if-busy +
        snapshot/RunState), Infrastructure Design SKIP (local CLI), Code Generation + Build&Test EXECUTE. Build on F2 branch/merge base.
  - **`/critic` adversarial review (isolated subagent) 2026-05-29 — 7 findings (2 HIGH), all cross-verified valid vs F2 code @ f63fad2.**
        Recorded as design constraints in requirements §11 (+ inline FR-2/FR-3/NFR-1 pointers, execution-plan NFR Design scope). All
        engineering refinements (no policy fork). Most load-bearing: **C-1 (HIGH)** skip-if-busy is a TurnCoordinator *modification* —
        `scheduled_turn()` is blocking and `_reconcile_waiting`≥1 while a wake turn runs, so the scheduled turn QUEUES not skips
        (turns.py:30-56); need an in-flight flag + `try_scheduled_turn()` + reconcile-yield-vs-skip distinction + integration test.
        **C-3 (HIGH)** the snapshot cache holds only positions_count+market_open and refreshes only at scheduled-turn tails
        (agent.py:70-80) → "account truth" + new-fill wake have no data; need an enriched payload (positions+open_orders+fills cursor)
        refreshed by a short-cadence CommandBus job + fill detection by broker diff. C-4 ReconcileWorker single run_fn/debounce/non-
        reentrant lock → per-trigger run_fn/prompt. C-5 watch.jsonl needs its own JSONL reader + persisted fired cursor (torn-line guard
        is private to read_decisions). C-6 news = per-symbol yfinance+15min cache → off-thread/bus poll. C-7 split gate inputs (market
        data direct, account via bus). C-8 paused short-circuits before the gate (suppression log must live in the wake detector) +
        entries_halted is a new hook + IntervalTrigger not wall-clock-aligned. These land in Functional/NFR Design.

## New Feature Track: Claude-Code-native Steering Console (F4 — replaces F2 front-end)
- **Started**: 2026-05-29. **Stage**: INCEPTION → Requirements Analysis (comprehensive-leaning), awaiting answers at the gate.
- **Goal (user)**: Replace the in-development F2 human-steering-console (`prompt_toolkit` REPL) with a **Claude Code
  session** that has custom commands registered; optionally a **customized opencode.ai** build. Aims: (1) easier natural-
  language command support, (2) tighter communication with the running intraday/research agent.
- **Feasibility grounding (read 2026-05-29)**: the PM trading agent is ALREADY a Claude Code session (`AgentSession` →
  `claude -p --resume`, daily/tools/advisor-only, `src/agent/session.py`). F2 (branch `feat/human-steering-console`,
  13 commits, 268 tests, NOT merged) already splits into a **daemon-side engine** (`src/agent/steering/{bus,commands,
  parser,records,state,turns}.py`) + a **front-end** (`steering/console.py`). **F2 NFR-1 already pre-designed a file-drop
  front-end reusing the same serialized CommandBus at near-zero cost** — a Claude Code operator session IS that front-end,
  and it resolves F2 requirements §6 (attached vs detached) toward detached. F3 reuses F2's TurnCoordinator/ReconcileWorker/
  SteeringState — so the daemon-side engine must survive whatever F4 decides (Q1/Q7).
- **Central tension surfaced**: Claude/opencode slash commands expand to LLM prompts → reintroduces nondeterminism into the
  safety-critical order path that F2 deliberately kept LLM-free (FR-2, SECURITY-15). Resolved via Q4.
- **Questions docs**: `steering-console-redesign-questions.md` (Q1–Q9) + `steering-console-redesign-clarification-questions.md`
  (Clarif-1/2). **Requirements doc**: `aidlc-docs/inception/requirements/steering-console-redesign.md`.
- **Decision set (2026-05-29):** Q1→Clarif-1=A (discard F2 branch code + `console.py` front-end + parser; KEEP the daemon-side
  safety architecture and reimplement it cleanly, Claude-Code-native + file-drop); Q2=B (opencode.ai fork as the operator TUI);
  Q3=A (file-drop JSONL command channel → single CommandWorker → existing RiskManager→Broker gate); Q4=B (NL trades allowed,
  LLM proposes only, deterministic 1-line echo + `y`/`CONFIRM` gate); Q5=A,C,D + partial B (read + event-push + lightweight
  two-way Q&A in v1, directive injection partial); Q6=A (fully detached operator process); Q7=C (abandon F2 branch as a
  deliverable, realign F3 onto F4's reimplemented engine); Q8=A–E (full command set) + **hard NFR-1: operator command authority
  structurally unreachable from research/intraday/PM agent sessions** (advisor-only; no write to the file-drop command channel /
  order path); Q9=A (project-default extensions); Clarif-2=B (opencode fork is a first-class v1 deliverable, contract + TUI together).
- **F3 realignment (Q7=C):** F4 reimplements the engine, so F3's prior critic findings (C-1 skip-if-busy, C-3 snapshot payload,
  C-4 per-trigger run_fn, C-5 shared JSONL reader+cursor, C-7 split gate inputs) get baked into F4's engine from the start;
  F3 rebases onto F4's engine as a follow-up.
- **Risk:** High–Medium (reimplementing the live order path; forking/maintaining opencode; cross-process IPC + privilege split).
  Mitigations: worktree isolation, contract-first headless CLI verification, F2 safety-model equivalence tests, privilege-deny tests.
- **Stage Progress (F4)**:
  - [x] Workspace Detection — reused (brownfield, existing project).
  - [x] Reverse Engineering — reused (artifacts already exist).
  - [x] Requirements Analysis — **APPROVED** 2026-05-29 ("나머지 승인"). Q1–Q9 + Clarif-1/2; one contradiction
        (Q1/Q7=C vs Q3=A) detected and resolved (Clarif-1=A). **Refinement on approval:** Q2 opencode = rebrand/repurpose
        into a trader-agent-owned tool (hard fork, NO upstream-tracking burden), not an upstream-following fork.
  - [x] Workflow Planning — **COMPLETE** 2026-05-29 (awaiting approval). Plan:
        `aidlc-docs/inception/plans/steering-console-redesign-execution-plan.md`. Risk **High–Medium**.
        **Stage determination:** User Stories SKIP, Application Design SKIP (→ Functional Design), Infrastructure Design SKIP
        (local). **Units Generation EXECUTE** (minimal) — unlike F2/F3, decompose into **2 units** because the two
        deliverables are different languages with a file-drop seam: **Unit A `steering-core` (Python)** = reimplemented
        daemon safety engine + file-drop command/event/read channels + privilege enforcement (F2 safety model + F3 critic
        C-1/C-3/C-4/C-5/C-7 baked in; headless-CLI testable), built FIRST; **Unit B `operator-tool` (TS/Go, opencode
        rebrand)** = trading-ops TUI over the contract, built SECOND. Per-unit Functional Design / NFR Requirements /
        NFR Design / Code Generation EXECUTE; Build and Test EXECUTE (F2 equivalence + privilege-deny + PBT + cross-process
        integration + full regression). New worktree+branch; F2 branch abandoned; F3 rebases onto Unit A after merge.
  - [x] Workflow Planning — **APPROVED** 2026-05-29 ("승인할게").
  - [x] Units Generation — **COMPLETE (minimal)** 2026-05-29 — 2 units confirmed (A `steering-core` Python first, B
        `operator-tool` opencode-rebrand second; file-drop contract seam). Defined inline in the execution plan §3.
  - **CONSTRUCTION — Unit A (`steering-core`):**
    - [x] Functional Design — **COMPLETE** 2026-05-29 (awaiting approval). FD questions all answered **A** (Q1=A channel at
          repo-root `steering/`; Q2=A confirmed-only records; Q3=A scheduler poll; Q4=A id-correlated outcomes; Q5=A full FR-8 gate).
          Artifacts: `construction/steering-core/functional-design/{domain-entities,business-logic-model,business-rules}.md`.
          Carries F2 safety model (BR-1..9, E1..6) into detached+file-drop; adds **E7 SteeringCommand / E8 SteeringEvent /
          E9 AgentQuestion + snapshot.json**; channel at repo-root `steering/` (commands/events/snapshot/.cursor); confirm moves
          to Unit B (daemon trusts confirmed-only). **New BR-10 privilege separation** = location + **operator token the agent
          never receives** (structural, since agent Write/Edit can target absolute paths) + advisor-only/approval-gate residual +
          optional PreToolUse hook confining agent writes to workspace. BR-11 file-drop idempotency/cursor (torn-line, persisted,
          id-dedup). F3 critic C-1/C-3/C-4/C-5 baked into the fresh engine.
    - **`/critic` adversarial review (isolated subagent) 2026-05-29 — 8 findings (2 HIGH, 4 MED, 2 LOW), ALL cross-verified valid
          vs `main` code; all engineering refinements (no policy fork), applied to the FD docs:** #1 [HIGH] operator token NOT
          structural — agent has unrestricted `Read` (absolute paths) + `env=dict(os.environ)` copy (session.py:189) can read a
          token in `steering/`/daemon-env → **BR-10 redesigned: PreToolUse workspace-confinement hook made the MANDATORY primary
          structural boundary; token moved out-of-band (operator-process only) + scrubbed from agent env**. #2 [HIGH] single-worker
          invariant narrower — scheduler-thread `execute_pending` + agent's own AlpacaBroker → BR-7.1'/7.2' (funnel scheduled
          executor through the worker; atomic cursor; agent broker is read-only). #3 [MED] TurnCoordinator/turn_lock absent on main
          (net-new, not inherited) + scheduler needs explicit max_instances/coalesce → BR-7.3'. #4 [MED] no `execute_decision`
          (only cursor-coupled `execute_pending`) → promote `_execute_one` (BLM §3.2). #5 [MED] cursor must be byte-offset + id-dedup
          authoritative (BR-11). #6 [MED] snapshot needs dedicated publisher + atomic write (BR-12.4). #7 [LOW] agent_questions
          writer/writer race → append-only + separate answers file (E9). #8 [LOW] emergency "즉시" overstated → ~11s bound (BR-13).
          Validated-as-sound: `_execute_one` is cursor-free, so BR-2 idempotency is achievable once exposed.
    - **opencode feasibility investigation (user-prompted at the gate) 2026-05-29** — clarified the runtime split (BR-10.1
          PreToolUse hook confines the AGENT=`claude`, a Claude Code feature, NOT opencode; opencode is the high-authority
          operator side). Findings in `construction/operator-tool/nfr-requirements/opencode-feasibility.md`: opencode HAS a
          permission system (allow/ask/deny, per-agent, `external_directory`) + plugin hooks (`tool.execute.before/after`, custom
          tools, `shell.env`) → **sufficient, conditionally**. Known security bugs to design around: #5894 (tool.execute.before
          doesn't intercept subagent/`task` calls → deny `task`), #7006/#19927 (`permission.ask` hook not triggered → don't rely
          on it), #6396 (SDK-invoked agent `deny` ignored → verify in fork). **Key (user's instinct):** the operator side is an LLM,
          so `confirmed=True` must be set by a deterministic layer (custom-tool execute fn does its own human confirm + token +
          atomic append) the LLM cannot forge; daemon-side confirmed+token+RiskManager remains the real boundary. Added a confirm-
          integrity clause to the Unit A FD seam (BLM §6).
    - [x] Functional Design — **APPROVED** 2026-05-30 ("승인. 다음 단계로 진행").
    - [x] NFR Requirements — **COMPLETE (minimal)** 2026-05-30 (awaiting approval). Artifacts:
          `construction/steering-core/nfr-requirements/{nfr-requirements,tech-stack-decisions}.md`. **Conclusion: 0 new runtime
          deps for Unit A** (prompt_toolkit/rich dropped — UI moved to Unit B/opencode). stdlib threading/queue + pydantic + existing
          APScheduler/loguru/executor reused; Hypothesis (dev) for PBT. BR-10.1 hook = Claude Code settings.json + a deterministic
          Python deny-script confining the agent's tools to `workspace/`; token out-of-band (operator env, scrubbed from agent env).
          Atomic writes via stdlib `os.replace`. No new question round. Deferred to NFR Design: serialization primitive (Lock vs
          queue worker), hook script form/load-path for headless `claude -p` (verification item), snapshot publisher cadence.
    - [x] NFR Design — **COMPLETE** 2026-05-30 (awaiting approval). Artifacts:
          `construction/steering-core/nfr-design/{nfr-design-patterns,logical-components}.md`. Adapts F2 P1–P6 to detached+file-drop
          with all critic fixes folded. **Deferred items resolved:** (1) serialization primitive = **`queue`-based single
          CommandWorker** (not bare Lock — 3 sources: file-drop poll / scheduler funnel / reconcile) with emergency/normal lanes;
          (2) snapshot publisher cadence = 2–5s job, separate from file-drop poll 1–2s; (3) hook = settings.json + deterministic
          Python deny-script (`realpath` confine to workspace for Read/Write/Edit/Glob/Grep; Bash stays allowlist+exec-form since
          parsing arbitrary bash paths is fragile), load-path a code-gen verification item, token scrubbed from `session._invoke`
          env. **Module decomposition** (`src/agent/steering/`): records/jsonl(shared C-5 reader)/channel/state/bus/turns
          (TurnCoordinator in-flight+try_scheduled C-1, ReconcileWorker per-trigger C-4)/commands/gate/security; existing-file edits
          (executor `_execute_one`→public `execute_decision`+atomic cursor, session env-scrub, modes/agent funnel+poll+publisher+drop
          console, scheduler max_instances/coalesce, journal→shared reader). Verification items + test strategy listed.
    - [x] Infrastructure Design — **SKIP** (local CLI/daemon, no cloud infra).
    - [~] Code Generation **Part 1 (plan)** — created 2026-05-30, **awaiting approval to enter Part 2**. Plan:
          `construction/plans/steering-core-code-generation-plan.md` (Steps 0–10: worktree → records/jsonl → state → channel →
          executor `execute_decision`+gate → bus → turns → commands → security(hook+token) → wiring → integration/PBT/regression).
          0 new runtime deps. On approval, Part 2's FIRST action = create git worktree+branch off main (Q8=A); no code/worktree yet.
          User pre-agreed: approve Part 1 plan, then Part 2 (code+tests) runs autonomously.
    - [~] Code Generation **Part 2 (build)** — APPROVED & in progress 2026-05-30 (worktree `.claude/worktrees/steering-core`,
          branch `feat/steering-core` off main). **Done (all green):** Step 0 worktree; **Step 1** records.py (E2/E6/E7/E8/E9 +
          AgentAnswer) + jsonl.py (torn-safe byte-offset reader + ByteCursor + atomic_write_text) + Decision.source — `tests/
          test_steering_records.py` 10 passed; **Step 2** state.py (RunState/HumanLock state-machine/PendingApproval/Directive +
          RLock + atomic ET-date persistence + lazy-expiry/sweep + counter rehydrate) — `tests/test_steering_state.py` 11 passed.
          **Step 3** channel.py (read_new_commands torn-safe + confirmed+token hmac validation + persisted processed-id dedup;
          emit_outcome/append_event/publish_snapshot atomic) — `tests/test_steering_channel.py` 7 passed; **Step 4** executor.py
          `_execute_one`→public `execute_decision` (cursor-free; off-hours queueing left to caller) + atomic cursor write; new
          `gate.py` gate_agent_decision (execute/park/deny, HOLD/ADJUST_STOP exempt BR-4.6) — `tests/test_steering_gate.py` 4 passed
          + executor regression 21 + **full suite 232 green** (live-order-path rename regressed nothing; no external `_execute_one`
          refs). **Remaining (Steps 5–10):** bus(queue/worker/lanes/funnel) → turns(TurnCoordinator/ReconcileWorker) →
          commands(verbs) → security(PreToolUse hook+token) → wiring(modes/agent/scheduler/journal/orchestrator) → integration.
          32 new steering tests green; still nothing wired into the live daemon (modules + the cursor-free executor entry point only).
    - **Part 2 progress (committed checkpoints on `feat/steering-core`):** `98b1f31` Steps 1–4 (records/jsonl/state/channel +
      executor gate); `0985b0e` Steps 5–6 (bus.py CommandBus single-worker + emergency lanes; turns.py TurnCoordinator
      try_scheduled_turn/reconcile_turn + ReconcileWorker per-kind+debounce). **42 new steering tests; full suite green.**
      **Remaining Steps 7–10:** commands.py (verb handlers wiring channel↔state↔executor↔broker, off-hours queue) →
      security.py (PreToolUse hook + token issue/scrub — **needs live `claude -p` verification, may need user env**) →
      wiring (modes/agent funnel+poll+publisher+drop console, scheduler max_instances/coalesce, journal shared reader,
      orchestrator reconcile) → integration/F2-equivalence/full regression. These touch the live daemon loop.
    - **`/critic` adversarial review of the CODE (steps 1–6) 2026-05-30 — 8 findings (2 HIGH, 3 MED, 3 LOW), all cross-verified
      vs code; all engineering refinements, applied (commit `48e71ca`):** #1 (HIGH) `execute_decision` has no market gate →
      documented the caller-must-gate/off-hours-queue contract loudly (enforced in step 7). #2 (HIGH) `CommandBus.stop()` could
      drop queued commands + hang waiters → post-stop submits rejected (error result) + queue drains. #3 (MED) approve/reject now
      ET-date-scoped like list_pending (no midnight drift). #4 (MED) `atomic_write_text` unique temp (pid+uuid) + failure cleanup;
      `channel.daily_reset()` added (re-scope processed-ids + archive commands.jsonl; wire into midnight sweep step 9). #5 (MED)
      `reconcile_turn` holds the waiting indicator through `run_fn` (scheduled yields with 'reconcile_waiting' even during a
      reconcile). #7 (LOW) `PendingApproval` stores the full `Decision` (not a lossy `DecisionLike`) → approved pendings keep
      confidence (sizing) + valid_until (expiry). Critic-verified-sound: byte reader multibyte safety, _Item ordering, token
      redaction. +5 regression tests; **full suite 247 green**. 3 commits on `feat/steering-core`.
    - [x] **Step 7 commands.py** — COMPLETE & committed (`a0fc86c`). CommandHandler dispatches every verb on the bus worker:
      build_human_buy (explicit $/sh floored + ATR bracket), sell/flatten via execute_decision (flatten cancels resting first),
      lifecycle (pause/resume/halt/allow/kill), approval (approve executes parked Decision + unlocks; reject increments),
      unlock/cancel/stop/note/directive/answer; each emits corr_id outcome + InterventionRecord; book changes trigger reconcile;
      off-hours trades market-gated → queued (channel.queue_offhours/drain_offhours, token redacted on disk). 12 new tests;
      **full suite 259 green.** 4 commits total (98b1f31, 0985b0e, 48e71ca, a0fc86c).
    - [x] **Step 8 security.py — COMPLETE & live-verified (`cf1d3ee`). `claude -p` hook-load PASS ✅ (user-run 2026-05-30):**
      the headless agent loaded the PreToolUse hook from `workspace/.claude/settings.json` and BLOCKED a read of an
      out-of-workspace 'operator_token' file (control in-workspace read succeeded); the agent reported "a security hook blocked
      the request… operator token is explicitly off-limits." **BR-10.1 confirmed real in headless mode** — privilege separation
      is structural, not assumed. No alternative (--settings/wrapper) needed.
    - [~] (superseded) Step 8 security.py — CODE COMPLETE & committed (`cf1d3ee`), live-claude verification PENDING.
      PreToolUse deny-hook (pure stdlib, standalone-runnable): denies Read/Write/Edit/Glob/Grep/Notebook paths resolving outside
      the agent workspace (BR-10.1) → agent can't reach repo-root steering/ or the token even via absolute path. + write_agent_hook_settings,
      issue_token, scrub_agent_env (BR-10.2). 5 unit tests + standalone smoke (inside→rc0 / outside→rc2) green. **Open item:** does
      headless `claude -p` load the hook from `workspace/.claude/settings.json`? → user runs `scripts/verify_steering_hook.py`
      (control reads in-workspace file = must succeed; attack reads out-of-workspace 'token' = must be blocked). If it FAILS, BR-10.1
      needs an alt (e.g. `--settings` flag / wrapper) before Step 9 wiring trusts the hook.
    - [x] **Step 9 wiring — COMPLETE & committed (`4914fd2`).** runtime.py SteeringRuntime (assembles engine + daemon jobs:
      poll_commands/publish_snapshot/drain_offhours/daily_sweep/poll_agent_questions; issues+exposes token, installs hook);
      modes/agent.py optional `steering=` (executor funnels through the single bus worker; scheduled turns via TurnCoordinator
      skip-if-busy; paused gate runs protective exits only BR-3.1; off-hours drain at open); scheduler max_instances/coalesce +
      add_seconds_job; journal shared torn-safe reader; session env token scrub; orchestrator.run_reconcile; `/answer` persists
      AgentAnswer to a separate file. 7 runtime integration tests. Full suite green.
    - [x] **Step 10 — COMPLETE & committed (`57038d6`).** main.run_agent builds SteeringRuntime + `--steering` flag (opt-in;
      without it the daemon is byte-for-byte unchanged, NFR-8); steering/ gitignored. **Full suite 271 green.** Code summary:
      `construction/steering-core/code/code-summary.md`.
    - **UNIT A `steering-core` CODE GENERATION COMPLETE & APPROVED** 2026-05-30 ("다음 단계로 진행, Unit B 시작하자") — 7 commits
      (98b1f31, 0985b0e, 48e71ca, a0fc86c, cf1d3ee, 4914fd2, 57038d6) on `feat/steering-core`; ~78 new steering tests; full suite
      271 green; 0 new runtime deps; privilege separation (BR-10.1) **live-verified** in headless `claude -p`. NOT merged.
  - **CONSTRUCTION — Unit B (`operator-tool`, opencode rebrand):**
    - [~] Functional Design — questions posed 2026-05-30 (`construction/operator-tool/functional-design/functional-design-questions.md`,
      7 forks: fork depth, confirm-critical write mechanism, read surface, event surfacing, token delivery, command set, extensions).
      **Research-grounded:** opencode custom commands = LLM prompt templates (not deterministic) → confirm-critical writes must use a
      **custom tool (plugin Zod+execute)** that owns confirm+token+append (LLM can't forge); reads can stay LLM-mediated; a
      `.opencode/` config+plugin distribution may avoid a heavy source fork. Known opencode bugs to design around: #5894 (task/subagent
      bypass → deny task), #7006/#19927 (permission.ask not triggered → don't rely on it), #6396 (SDK deny ignored → verify).
      Awaiting answers. Pre-finding doc: `construction/operator-tool/nfr-requirements/opencode-feasibility.md`.

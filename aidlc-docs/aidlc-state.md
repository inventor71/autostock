# AI-DLC State Tracking

> **Layout change (2026-05-31): concurrent multi-track partition.** This root file is now the
> **Track Registry** (the table below). New tracks keep their full state + audit in
> `aidlc-docs/tracks/<id>/{state.md,audit.md}` (single writer per track) — see
> `.aidlc-rule-details/common/concurrent-tracks.md`. Everything **below the registry** is the
> **archived pre-partition history** (F1–F8 + refactor), kept as record; do not add new per-track
> detail to it.

## Track Registry
| ID | Title | Status | Branch | Worktree | Submodule branch | Base | Updated |
|----|-------|--------|--------|----------|------------------|------|---------|
| F1 | Dynamic Intraday Pattern Detection | merged | — | — | — | — | 2026-05-28 |
| F2 | Human-Steering Console (agent mode) | abandoned | feat/human-steering-console | — | — | — | 2026-05-30 |
| F3 | Intraday Loop Redesign | merged | feat/intraday-redesign | — | — | 95f94d1 | 2026-05-30 |
| F4 | Claude-Code-native Steering Console | merged | — | — | feat/* | 1719fcf | 2026-05-30 |
| F5 | Console-native Launcher & Rebrand | merged | — | — | merged→origin | aaf01e2 | 2026-05-30 |
| F6 | Console Sidebar Upgrade | active | feat/console-sidebar-upgrade | — | — | — | 2026-05-30 |
| F7 | Trading-native home copy | merged | — | — | merged→main | 631ec6e | 2026-05-31 |
| F8 | Console Sidebar Status Rich | merged | feat/console-sidebar-status-rich | — | merged→fork main 2ac0cda | 77d5ed9 | 2026-05-31 |
| R1 | New-surface refactor review | active | (TBD) | (TBD) | — | — | 2026-05-31 |
| M1 | AI-DLC multi-track customization | active | main (rules/docs) | — | — | 631ec6e | 2026-05-31 |
| F9 | Alpaca-format console orders (limit/stop/TIF) via risk gate | merged | feat/F9 | — | — (parent-repo only; opencode perm keys = follow-up) | e8d99a6→8948e24 | 2026-05-31 |
| F10 | Containerized verification harness (zero prod impact) | merged | feat/docker-verify | — | — | 8ff59c0 | 2026-05-31 |
| F11 | Verify-harness ergonomics (clean worktree + reuse main .env.test) | merged | feat/verify-ergonomics | — | — | 24dc367 | 2026-05-31 |
| F12 | Verify-harness hardening (critic: account pin + fail-closed preflight) | merged | feat/verify-hardening | — | — | 715723e | 2026-05-31 |
| F13 | Sidebar fills date + blank line between sections | merged | feat/F13 | — | merged→fork main aa984da | a7a9ea1 | 2026-05-31 |
| F14 | Daemon wedge self-heal + WakeDetector market-data fetch rigidity | merged | feat/F14 | — | — | d899f83 | 2026-05-31 |
| F15 | docker-verify `attach` mode (full daemon+TUI runtime, TEST account) | merged | feat/F15 | — | — | 98090fa | 2026-05-31 |
| F16 | Broker API adapter — trade the sandbox account farm | active | feat/F16 (TBD) | .claude/worktrees/F16 (TBD) | — | cc125e5 | 2026-05-31 |
| F17 | docker-verify cleanup — sudo-free teardown (ownership handback) | merged | feat/F17 | — | — | f912999 | 2026-05-31 |
| F18 | docker-verify attach console-MCP env wiring (AUTOSTOCK_ROOT + shared token) | merged | feat/F18 | — | — | 6902612→8f5468c | 2026-05-31 |
| F19 | F9 follow-up: 6 structured-tool opencode permission keys in fork config | merged | feat/F19 | — | merged→fork main bc82b71 | 2f13a7a→a1851e0 | 2026-05-31 |
| F20 | Alpaca-shaped read tools (arbitrary-symbol quote/orders) — fix console read limit | merged | feat/F20 | .claude/worktrees/F20 | feat/F20 (opencode perm keys) | 79df84a→093f11e | 2026-05-31 |
| F21 | Synchronous MCP arg validation (3-layer: zod .refine() → degenerate check → daemon defense-in-depth) | merged | feat/F21 | .claude/worktrees/F21 | — (parent repo: mcp-server.ts + commands.py) | 79df84a→0ed7044→merge | 2026-05-31 |
| F22 | AI 협업 TUI 개선 — AI(research/intraday) 협업 특화 UI/UX | merged | feat/F22 | .claude/worktrees/F22 | feat/F22 | 620eeac→5968d9b→ab6e742 | 2026-06-01 |
| F23 | Multi-Agent Research 교차검증 + 시그널 확장 | active | feat/F23 (TBD) | .claude/worktrees/F23 (TBD) | — | TBD | 2026-06-01 |
| F24 | Decision Quality Metrics — 에이전트 결정 품질 정량 분석 | merged | feat/F24 | — | — | e0a345b→b4fa955 | 2026-06-01 |

> Status: `active` / `merged` / `abandoned`. Edit a row only at track **create** / **merge/close**
> (the only cross-track writes — serialize with `git pull --rebase`). Historical F1–F8 rows were
> reconstructed from the archived history below at migration time and may be approximate; the
> per-track files under `tracks/` are authoritative for any track started after the migration.

---

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
  - **[/ai-dlc-resume] Integration-base RECONCILIATION 2026-05-30 (F4 merged to main).** F3 was designed against the **unmerged
        F2 engine @ f63fad2**; F4 reimplemented that engine and **merged it to `main`** (merge `1719fcf`). Re-verified the §11 critic
        findings against `main/src/agent/steering/`: **C-1 DONE** (`turns.py:37 try_scheduled_turn`, in-flight flag split from waiter
        count, reconcile-priority; wired at `modes/agent.py:70`), **C-4 DONE** (`ReconcileWorker.trigger(kind=)` per-kind), **C-5 DONE**
        (`jsonl.read_complete_lines`+`ByteCursor`). **C-3 MOSTLY DONE** (`runtime.publish_snapshot` ships positions+open_orders on a
        5s bus job, `modes/agent.py:181`) — **remaining: fills cursor / new-fill diff** for FR-4-A. **C-6 (news infra) / C-7 (split
        gate inputs) unchanged net-new. C-8 PARTIAL** — `RunState`+`_paused()` wired in the scheduled path; **`entries_halted` has no
        consumer yet** (new hook) + wake-path paused-hold/suppression-log net-new. Net: **F3 scope shrank** (riskiest concurrency
        already merged); base = **worktree off `main`** (F2 branch abandoned per F4 Q7=C). Docs updated: requirements §11.0 table +
        §1/§5/NFR-3; execution-plan banner + Component/Risk lines. **Next = CONSTRUCTION → Functional Design (EXECUTE) on the main base.**
  - **CONSTRUCTION — Unit `intraday-redesign`:**
    - [x] Functional Design **Part B answered** 2026-05-30 — all 8 = recommended defaults: **Q1=A** (new `watch set/clear`
          agent tool, sole writer of `workspace/watch.jsonl`), **Q2=A,B** (`price_above/below` + `close_above/below`),
          **Q3=A** (broker fills/activities cursor via `get_fills(since)` → snapshot payload; truth, not qty-diff inference),
          **Q4=A(i)** (ATR×k OR vol×m, `config/settings.yaml` `intraday.abnormal_move` block), **Q5=A** (coalesce multi-wake
          into ONE wake turn), **Q6=A** (compact structured text brief), **Q7=B** (entries_halted = keep firing + inject
          "no new entries" prompt; final block stays `gate_agent_decision` — NOT kind-based suppression), **Q8=B** (news diff
          over held + watched symbols, ≥15min TTL).
    - [x] Functional Design **artifacts generated** 2026-05-30 (awaiting approval). Grounded against main `src/agent/steering/`
          (turns.py try_scheduled_turn/ReconcileWorker.trigger(kind=), runtime.publish_snapshot, gate, state RunState).
          `construction/intraday-redesign/functional-design/{domain-entities,business-logic-model,business-rules}.md` (UI 없음→frontend 생략).
          **Entities:** E1 WatchTrigger (jsonl, agent-tool-written, fired/valid_until cursor) · E2 IntradayBrief (transient,
          market=daemon-direct / account+fills=snapshot-cache, C-7) · E3 WakeEvent (4 kinds, coalesced) · E4 SnapshotDelta/FillDelta
          (fills-cursor based, C-3 잔여) · E5 NewsDiff · E6 AbnormalMoveSignal; + main reuse boundary (RunState/snapshot/ByteCursor/
          TurnCoordinator/ReconcileWorker/gate — no new concurrency primitive). **Key FD finding:** main `ReconcileWorker._fire`
          fires each *kind* as a SEPARATE reconcile_turn → Q5=A "one turn" needs a single `wake` kind whose run_fn drains a
          typed-event buffer into one prompt (noted in BLM-2/BR-9). F3 net-new = brief assembly + wake detector (new_fill/abnormal/
          watch/protective) + news poller + watch.jsonl + fills-cursor snapshot ext + entries_halted prompt hook; concurrency/JSONL/
          snapshot skeleton inherited from main.
    - **`/critic` adversarial review (isolated subagent) 2026-05-30 — 8 findings (HIGH 3, MED 4, LOW 2), ALL cross-verified
          valid vs `main` code; reflected into the FD docs:** #1 [HIGH] `_with_human_context` **does not exist** — F4 injects
          human context (`_recent_context`) only into `run_reconcile` (`runtime.py:75`), NOT intraday/scheduled/wake → BriefAssembler
          must BUILD it (directives/pending/locks) as net-new, not "preserve" (E2/BLM-1/BR-5.3). #2 [HIGH] Q5=A coalesce can starve
          the human reconcile — `ReconcileWorker` debounce timer is **kind-shared** (`turns.py:99-101`) + `_fire` sequential (`:110`,
          600s timeout) → split wake/human lanes (or per-kind timers) + shorten wake timeout + typed-event buffer is WakeDetector-owned,
          drained at fire time (BLM-2/BR-9; ReconcileWorker is a *modification*, not pure reuse). #3 [HIGH] `get_fills` must be
          `GetActivitiesRequest(FILL)` — existing `_alpaca_fills` is order-level (`get_orders`, `trades_log.py:45`), no per-fill id /
          partial-fill blind → net-new broker work (E4/BLM-6/BR-7). #4 [MED] entries_halted "gate blocks BUY" is **false** —
          `gate_agent_decision` only checks human locks (`gate.py:8,33-49`), no entries_halted consumer anywhere. #5 [MED] `ByteCursor`
          has no date scoping (integer offset, `jsonl.py:67-84`) → fired tracking needs separate `{et_date, fired_ids}` (E1/BR-6.4/6.5).
          #6 [MED] `outcome_lines` calls `broker.get_position` directly (`review.py:42`) → reuse formatting only, data from snapshot
          (BR-5.4). #7 [MED] ATR(14) needs intraday bars; `data_provider.get_bars` uncached + yfinance rate-limited → bar cache 1–5min,
          separate from pure ATR math (E6/BR-8). #8 [LOW] `run_intraday` called with no args (`agent.py:110`) → brief needs builder +
          signature + call-site wiring (BLM-1/3). Validated-as-sound: try_scheduled_turn skip-vs-yield, `_paused()` on scheduled path,
          5s snapshot bus job + atomic write.
          **Policy forks resolved by user:** **#4 → Q7=A** (entries_halted = WakeDetector suppresses `entry_inducing` wakes; gate stays
          out of it since it truly doesn't block — REVERSES the earlier Q7=B), **#3 → activities API adopted** (`GetActivitiesRequest(FILL)`,
          new broker port). Other 6 = engineering refinements folded into FD docs. F3 net-new (post-critic) = BriefAssembler
          (market-direct + snapshot account/fills + **human-context** + delta + news) · WakeDetector (new_fill via activities cursor /
          abnormal-move with bar cache / watch / protective; **entry_inducing suppression when halted**) · news poller · watch.jsonl
          (+`watch set/clear` tool, fired-set {et_date,fired_ids}) · snapshot fills-event ext · **ReconcileWorker lane/timer mod** ·
          broker `get_fills` activities port.
    - [x] Functional Design — **APPROVED** 2026-05-30 ("다음 단계로 진행"). Construction running autonomously per
          [[feedback-autonomy-construction]] (NFR Req → NFR Design → Code Gen Part 1, stop before worktree).
    - [x] NFR Requirements — **COMPLETE (minimal)** 2026-05-30 (awaiting approval). Artifacts:
          `construction/intraday-redesign/nfr-requirements/{nfr-requirements,tech-stack-decisions}.md`. **Conclusion: 0 new runtime
          deps** (stdlib threading/queue/json + pydantic/loguru/APScheduler/alpaca-py/yfinance reused; Hypothesis dev). **alpaca-py
          0.43.2 verified**: `GetActivitiesRequest` absent from the *Trading* client (Broker client only), but `TradeActivity` model +
          `ActivityType.FILL` exist → `get_fills` via raw `TradingClient.get("/account/activities", …)` (inherited RESTClient.get),
          still 0 new deps but a paper-account live-verify item (R1). Deferred to NFR Design: ReconcileWorker lane/timer, snapshot fills
          payload, bar cache cadence, brief threading, wake detector cadence, entry_inducing placement, fired-set form.
    - [x] NFR Design — **COMPLETE** 2026-05-30 (awaiting approval). Artifacts:
          `construction/intraday-redesign/nfr-design/{nfr-design-patterns,logical-components}.md`. P1–P6 adapted from F2/F4 with all
          critic fixes. **7 deferred resolved:** (1) ReconcileWorker **per-kind timers** (`dict[str,Timer]`, kills wake→human
          starvation) + wake-lane timeout ~120s + WakeDetector-owned buffer drained at fire time; (2) `publish_snapshot` adds `fills`
          events + `.fills.cursor` (bus-worker `get_fills`, id-dedup); (3) **BarCache** 60s stale + pure ATR/avg split; (4) BriefAssembler
          runs inside the turn run_fn (scheduled/wake thread), snapshot+data_provider only, **no `outcome_lines`** (it calls
          `broker.get_position`); (5) `agent_wake` 5s APScheduler job → detect_wakes (non-blocking trigger only, market data direct,
          account via snapshot); (6) `classify_entry_inducing` pure fn in WakeDetector, fail-closed True; (7) fired-set
          `watch_fired.json{et_date,fired_ids}` swept by the existing 0:01 `daily_sweep`. New modules `src/agent/intraday/{records,
          watch_store,bars,abnormal,brief,news_diff,wake}.py` + `watch` tool + broker `get_fills` (base no-op + Alpaca raw GET) + 6
          workspace data files + settings `intraday:` block; edits to turns/runtime/orchestrator/prompts/modes-agent/brokers.
          Concurrency table maps thread→broker/market/turn_lock so NFR-1/NFR-2 invariants hold. Infra Design SKIP (local daemon).
    - [x] Infrastructure Design — **SKIP** (local CLI/daemon, no cloud infra).
    - [~] Code Generation **Part 1 (plan)** — created 2026-05-30, **awaiting approval to enter Part 2**. Plan:
          `construction/plans/intraday-redesign-code-generation-plan.md` (Steps 0–11: worktree → records → broker get_fills → snapshot
          fills → watch+tool+fired-set → bars/abnormal → BriefAssembler → news poller → WakeDetector+ReconcileWorker lane → orchestrator/
          prompts → modes/agent+settings wiring → integration/PBT/regression+R1 live). 0 new deps. On approval, Part 2's FIRST action =
          `git worktree add … -b feat/intraday-redesign main`; no code/worktree yet.
    - **`/critic` 2nd review (NFR Design + Code Gen plan, isolated subagent) 2026-05-30 — 8 findings (HIGH 3, MED 4, LOW 3),
          ALL cross-verified valid vs `main`; reflected into NFR Design + plan (engineering only, no policy fork):** #1 [HIGH]
          per-kind timers DON'T "solve" starvation — the real serialization point is the single `turn_lock`; `_fire` calls
          `reconcile_turn` sequentially (`turns.py:110-112`), so human waits ≤ one in-flight wake turn (inherent/non-preemptible,
          = CQ-R1). Fix: per-kind timers only kill the *indefinite cancellation* starvation; `_fire` dispatches human-kind first;
          state the one-turn wait honestly. #2 [HIGH] the "120s wake timeout" path doesn't exist — `_fire` passes no timeout
          (`turns.py:112`) and `reconcile_turn` timeout is *acquire*-only, not execution (`turns.py:53,70`) → bound wake execution via a
          turn-level `_run(timeout=)`; plumb kind→timeout. #3 [HIGH] `detect_wakes` does blocking market-data network on the
          APScheduler default pool; `coalesce=True` (`scheduler.py:12`) silently drops wake ticks if a tick overruns 5s → detect_wakes
          reads cached data only (BarCache + short price TTL) + `misfire_grace_time`/dedicated executor. #4 [MED] snapshot is file-only
          (`channel.py:178`, no in-proc getter) → add `SteeringRuntime.last_snapshot` in-proc dict, brief reads memory not file;
          empty-snapshot fail-closed. #5 [MED] `get_fills` on the bus is delayed behind emergency/long batches → new_fill staleness
          bounded by bus backlog; ACCEPTED (OCO protection mechanical, fill *awareness* lateness is safe). #6 [MED] `held_symbols()`
          calls `portfolio_provider()`→broker on the turn thread (`orchestrator.py:62-70`) → F3 brief/wake derive held from snapshot
          positions, not held_symbols. #7 [MED] steering=None degrade undefined → `_intraday` falls back to legacy
          `intraday_prompt(quotes,held)`, wake/news off (NFR-8 preserved). #8/#9/#10 [LOW] base broker path is `src/execution/base.py`
          (get_fills concrete no-op safe, verified); `/account/activities` must NOT include `/v2` (get prepends version); Step 2
          monkeypatch tests assume response shape → R1 live is authoritative. Edits: nfr-design-patterns.md (P1/P2/P5/P7+table),
          logical-components.md (file-edit table+brief+broker path), tech-stack-decisions.md (/v2), code-generation-plan.md
          (Steps 2/3/5/6/8/9/10/11+surface). **Decisions taken (flag if disagree):** #5 keep get_fills on bus, #7 legacy fallback when
          steering off. **Gate: approve Part 1 plan to start coding.**
    - [x] Code Generation **Part 1 (plan) — APPROVED** 2026-05-30 ("시작하자"; turn_lock kept per user decision — removal would
          require a session-model redesign, deferred, not even backlogged as a separate feature until observed pain).
    - [x] Code Generation **Part 2 (build) — COMPLETE** 2026-05-30 on worktree `.claude/worktrees/intraday-redesign`, branch
          `feat/intraday-redesign` off main (e231015). **All Steps 0–11 green; full suite 282 → 346.** Commits: `826335a` (S1 records +
          S2 broker get_fills activities), `e58e7ee` (S3 snapshot fills + last_snapshot in-proc), `625371e` (S4 watch store/tool/fired-set
          + S5 bars/abnormal PBT), `1029451` (S6 BriefAssembler + S7 NewsPoller), `18e77cb` (S8 WakeDetector + ReconcileWorker per-kind
          timers), `124e725` (S9 orchestrator run_intraday(brief)/run_wake + prompts), `fbd174d` (S10 daemon wiring + IntradayConfig +
          settings.yaml + scheduler misfire_grace), `32fdab5` (S11 integration + DESIGN §5.8.1/README).
          **New:** `src/agent/intraday/{records,watch_store,bars,abnormal,brief,news_diff,wake,settings}.py` + `watch` agent tool + 13
          test modules (incl. Hypothesis PBT). **Modified:** steering/turns.py (per-kind timers — note: chosen over the planned "_fire
          human-first dispatch" because per-kind timers make batch-ordering moot; human has an independent timer so it's not starved,
          while the single turn_lock keeps the inherent one-turn wait), steering/runtime.py (snapshot fills + last_snapshot), orchestrator
          (brief/run_wake/held-from-snapshot), prompts (brief/wake_prompt), modes/agent (F3 wiring + steering=None legacy fallback),
          scheduler (misfire_grace_time=30), execution/base + alpaca_broker (get_fills), config (intraday block). **Invariants held:**
          advisor-only, decisions.jsonl→gate→RiskManager→Broker unchanged, 0 new runtime deps, agentic path not backtested.
          **R1 live verify — DONE & PASSED 2026-05-30** (run directly, market closed, read-only `/account/activities`): raw GET returns
          a list of 14 FILL dicts (keys id/activity_type/transaction_time/type/side/symbol/qty/price/cum_qty/leaves_qty/order_id/
          order_status); **activity `id` is `<seq>::<uuid>`, unique even for `type=partial_fill`** → idempotency-by-id holds and partial
          fills are NOT collapsed (the exact Q3=A goal the order-level `_alpaca_fills` couldn't meet); `after` cursor filters strictly
          newer; RFC3339(Z) `transaction_time` parses. Real shape locked into `test_intraday_fills.py` (commit 072f6ac). Known limit:
          single-page GET (≤100/poll; fine with a recent `after` cursor). Monkeypatch assumptions matched reality. **Full suite 347 green.**
          Build & Test stage + merge decision = next.
    - [x] **Build and Test — COMPLETE** 2026-05-30 (awaiting approval to proceed to Operations). Instruction docs:
          `construction/build-and-test/intraday-redesign/{build-instructions,unit-test-instructions,integration-test-instructions,
          performance-test-instructions,build-and-test-summary}.md`. **Results captured:** build import-smoke OK + `pip check` clean (0 new
          deps); F3 unit tests **65 passed** (11 modules incl. Hypothesis PBT); **full regression 347 passed** (282 baseline + 65, 0
          regressions); integration seams green (wake-through-real-engine, skip-if-busy V3, daemon wiring, steering=None fallback);
          **R1 live PASSED & pinned**; perf/load = N/A (single local daemon) with NF-1..5 concurrency/responsiveness guards documented;
          Security Baseline applicable rules met (SECURITY-03/-15). Invariants held.
          merge decision = next (after the code review below).
    - **`/code-review` (high effort, recall-biased) 2026-05-30 — 9 findings fixed (commit f6c7656; 347 → 356 green).**
          3 parallel finder agents (line/removed/cross-file · concurrency/cursor/state · cleanup/altitude), main-verified vs code.
          **Correctness:** #1 wake `_fill_events` had no dedup latch → a fill lingering in `last_snapshot['fills']` across detect
          ticks woke repeatedly → fill_id latch. #2 watch `mark_fired` ran at DETECT → a timed-out/never-run wake silently consumed a
          watch for the day → deferred to `_fire_wake` + `_pending_watch` guard. #3 `_to_fill_event` naive fallback vs tz-aware broker
          ts → `max(f.ts)` crash + cursor wedge + naive `after=` cursor → tz-aware fallback (+FillEvent default) + guarded
          `_collect_new_fills`. #4 abnormal anchor was the rolling-window oldest bar (~4h-stale, drifting) → `util.session_open`. #5
          watch tool wrote `Journal()` default root while daemon read `executor.journal.root` → tool uses daemon-exported
          `AGENT_JOURNAL_ROOT`. #6 `avg_volume` self-inflated by the current bar → excluded. #7 `news_diff.diff_for` KeyError race →
          snapshot `items()`. **Cleanup:** #8 WatchStore full-reparse + unsynchronized fired-set RMW on the 5s hot path → incremental
          tail-read cache + in-memory locked fired-set; #9 shared `util.held_and_watched`/`session_open`, dead news dict branch removed.
          Validated-sound: ReconcileWorker per-kind timer lock discipline; run_intraday fallback + call sites. 9 new tests.
    - [x] **MERGED to `main` 2026-05-30** — merge commit `95f94d1` (`--no-ff` of `feat/intraday-redesign` f6c7656 onto main fab3756;
          clean, main had only docs commits since the e231015 base). Post-merge: import OK, **full suite 356 green**. F3 track DONE.
          **Coordination note for F6** (`feat/console-sidebar-upgrade`, NOT merged): it also adds `get_fills` + extends
          `publish_snapshot`/`modes/agent` on the same 4 files — F6 must now rebase onto this main and unify its round-trip `get_fills`
          (dict for `match_round_trips`) with F3's activities `get_fills` (`list[FillEvent]`). F5 (`console-native-launcher`) is
          independent (0 shared files). Not pushed to origin (left to the user).

## New Feature Track: Claude-Code-native Steering Console (F4 — replaces F2 front-end)
> **STATUS (2026-05-30): DONE & merged to `main` (merge `1719fcf`).** This is the INCEPTION/design
> record; two framings below are SUPERSEDED by what shipped: (1) the title "Claude-Code-native" —
> F4 shipped as an **owned opencode hard-fork** console (per Q2=B in this same section), NOT a Claude
> Code session; (2) the console is **NL-only** — a second model-free keystroke command path was built
> then **removed** during construction (both paths shared the same confirm+RiskManager→Broker gate, so
> cleanliness won). **Authoritative final state = the "Steering Console Redesign (F4)" section at the
> END of this file** + project memory `steering-console-redesign.md`. For **F3**, you do NOT need to read
> this section — the distilled F4 impact (which critic findings F4's merged engine already satisfies) is
> in the F3 track's "Integration-base RECONCILIATION" entry above.
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
    - [x] Functional Design — **COMPLETE** 2026-05-30 (awaiting approval). FD questions answered: **Q1=B′ (opencode HARD FORK)**,
      Q2=A (deterministic action layer owns confirm+token+append), Q3=A (deterministic read commands/panels), Q4=A (background
      events.jsonl tail → push notifications), Q5=A (token via env inheritance), Q6=A–E (full command set), Q7=A (defaults + version
      pin + license + compile-time tool-removal verification). Q1 was reframed mid-stage (user insight): "opencode no-fork" is
      dominated by Claude Code (no-fork) — the real choice is Claude Code(A′) vs opencode hard fork(B′); user chose **B′** for a
      dedicated trading TUI + an LLM-bypass deterministic command path + **compile-time removal of side-effect tools** (turns the
      opencode permission bugs #5894/#6396 from "mitigate" into structurally impossible) + push UI + a branded binary.
      Artifacts: `construction/operator-tool/functional-design/{domain-entities,business-logic-model,business-rules,frontend-components}.md`.
      **Key locked decisions:** consumes/produces Unit A's file-drop contract unchanged (E7/E8/snapshot, repo-root steering/, token via
      env); LLM has NO order-path authority (NL→CommandDraft only; promotion to confirmed+token+append is owned by a deterministic
      layer / TUI confirm modal the LLM can't forge or bypass — BR-B1/B3); fork strategy = add trading panels + deterministic command
      path + events tail + `steer` action, REMOVE task/file-write/bash/web tools at compile time (BR-B4), rebrand binary, pin baseline
      (no upstream tracking); daemon-side Unit A remains the real safety boundary (defense-in-depth). **Note:** B′ is a TS/Go new-language
      deliverable + a 2nd LLM runtime — Code Gen will need a fork/vendoring spike (larger lift than Unit A).
    - [x] NFR Requirements — **COMPLETE** 2026-05-30 (awaiting approval). Artifacts:
      `construction/operator-tool/nfr-requirements/{nfr-requirements,tech-stack-decisions,opencode-feasibility}.md`. **Base verified:**
      opencode = `github.com/sst/opencode`, **MIT** (fork/rebrand allowed w/ notice), **TS core (Bun) + Go TUI (Bubble Tea)**.
      Tech stack (NEW vs Unit A's 0 deps): own the fork (Bun+Go toolchain), pin a baseline commit/tag (SECURITY-10, no upstream
      tracking). file-drop interop: TS reads/writes repo-root steering/; **TS types hand-maintained + a cross-language contract test**
      (Unit A pydantic is authoritative). Compile-time tool removal (BR-B4) = SECURITY-11. Token via `process.env`. Tests: bun/vitest
      (parser/token/confirm) + contract test; Python suite unaffected (separate process/lang). **Mandates a fork-feasibility SPIKE as
      Code-Gen Part-1 item #1** (confirm repo/tag, custom-tool deterministic execute, compile-time tool-removal point, a custom TUI
      pane PoC, build/run) to retire the largest unknowns before full build. No new question round (decisions follow from B′ + MIT +
      defaults; remaining unknowns are spike-resolved engineering, not user forks). Deferred to NFR Design: process/threading model
      (events-tail × TUI loop), schema-sync mechanism, compile-time-removal pattern.
    - [x] NFR Design — **COMPLETE** 2026-05-30 (awaiting approval). Artifacts:
      `construction/operator-tool/nfr-design/{nfr-design-patterns,logical-components}.md`. **Patterns:** P-B1 Bubble Tea single
      update loop + background goroutines (events-tail/snapshot-poll) injecting tea.Msg (no model race); **P-B2 single deterministic
      write path owned by the Go TUI** — parser→ConfirmModal→token+append; the TS LLM only *proposes* a CommandDraft (never writes/
      forges confirmed/token); **⚠ spike-contingent** (client↔server "propose-only" flow; fallback = TS `steer` tool execute owns
      confirm); P-B3 compile-time tool removal (task/bash/edit/write/webfetch unregistered → #5894/#6396 structurally impossible) +
      a registered-tools==allowlist assertion test; P-B4 schema mirror + `steering/contract-samples/` golden + cross-language contract
      test (Unit A pydantic authoritative); P-B5 O_APPEND atomic write (Unit A torn-line/id-dedup absorbs); P-B6 token via env (write
      UI gated); P-B7 resilience (tail/poll/write failure → warning, never kills TUI). logical-components: Go panels/parser/confirm/
      filedrop-writer/tail + TS schema/steer-fallback + base mods (registry removal, rebrand, client↔server) + thread/process model +
      test strategy. **Code-Gen entry = the fork-feasibility spike first** (resolves P-B2/P-B3 form + file paths).
    - [x] Infrastructure Design — **SKIP** (local TUI, no infra).
    - [~] Code Generation **Part 1 (plan) — created 2026-05-30, awaiting approval to run the spike.** Plan:
      `construction/plans/operator-tool-code-generation-plan.md`. Spike-first: **Phase 0 fork-feasibility spike** (S0.1 repo/MIT/tag
      pin, S0.2 Bun+Go build/run, S0.3 custom-tool deterministic execute, S0.4 tool-registry removal point, S0.5 custom TUI pane PoC,
      **S0.6 client↔server propose-only flow → decides P-B2 (Go-owned write vs TS steer fallback)**, S0.7 file-drop I/O + 1-line
      round-trip with Unit A) → go/no-go gate → **Phase 1 vertical slice** (`/pause` end-to-end: parser→confirm→token+append→outcome
      + statusbar/positions + token gate) → **Phase 2** full command set + panels + NL path → **Phase 3** compile-time tool removal +
      allowlist test + rebrand → **Phase 4** Go/TS unit + cross-language contract test (golden samples) + integration. Fork lives in a
      separate codebase (side repo `autostock-console` or `operator-console/` subtree — spike decides); Python suite unaffected.
      Risk High–Medium (new TS/Go base ownership, spike-dependent). On approval, Part 2 = run the spike first.
    - **Console LLM auth decision (2026-05-30, user):** keep B′ + plan unchanged, but the console connects to a **non-Anthropic model
      (OpenAI GPT-5.5 via its own OAuth)**, NOT the Claude subscription. **🚫 hard constraint: never use the Claude Pro/Max subscription
      in opencode** — Anthropic blocked third-party-harness subscription use (ToS violation → account ban; opencode removed Anthropic
      refs after a legal request), and a ban would kill the trading agent (same account). agent=Claude subscription, console=OpenAI
      OAuth (auth separated). NL→verb is light/optional; the deterministic path uses no LLM. Added spike item **S0.8** (verify OpenAI
      OAuth auth in opencode) + the no-subscription constraint to the plan/tech-stack. **Code Generation Part 1 (plan) APPROVED**
      ("이대로 유지, 플랜은 그대로").
    - [~] Code Generation **Part 2 — Phase 0 spike: static-analysis half DONE (2026-05-30), live half in progress.**
      Env: git/network/node OK; **bun 1.3.14 now installed (user)**, go NOT installed (not needed). Shallow-cloned sst/opencode
      (HEAD `16cae9a`). **MAJOR CORRECTION: current opencode is pure TS/Bun + OpenTUI (Go = 0 files); the earlier Go/Bubble Tea
      NFR-Design assumption is wrong → only Bun needed.** Static findings: S0.1 ✅ MIT/sst/TS-Bun-OpenTUI; S0.3 ✅ plugin Plugin +
      tool.execute.before + ToolDefinition (custom tools); S0.4 ✅ `tool/registry.ts` = single compile-time tool-removal point;
      S0.5 ✅(static) `TuiPluginApi` (tui.ts:581) render(JSX pane)/replace(modal)/toast(notify) → panels via plugin ('thin fork');
      S0.6 ✅ in-process TS → **P-B2 base case confirmed** (TuiPlugin owns input→confirm→write; LLM proposes only; no fallback);
      S0.8 generic `Oauth` schema present. Updated plan/tech-stack/nfr-design (Go→TS/Bun/OpenTUI/TuiPlugin/registry.ts). Live half:
      **Phase 0 SPIKE COMPLETE & GREEN (2026-05-30): user confirmed all 3** — `bun install` OK (after build-essential), `bun dev` launches the opencode TUI from source (S0.2/S0.5), and **OpenAI OAuth connects** (S0.8). Toolchain = **Bun + build-essential (make/gcc/python3)**; no Go. Net spike verdict: **thin TS fork** — panels/modal/toast via TuiPlugin, side-effect tools removed in registry.ts, P-B2 base case (deterministic write owned by the console, LLM proposes only). → entering Phase 1 vertical slice.
    - [~] **Phase 1 vertical slice — core DONE & verified (committed `4f68c64`).** `operator-console/` (TS, in the steering-core
      worktree): `schema.ts` (E7/E8 mirror), `parser.ts` (deterministic command parser, BR-B5, fail-closed), `filedrop.ts`
      (token-from-env attach + atomic append + torn-safe event tail + snapshot read, BR-B2/B5/B6), `console-stub.ts` (interactive
      readline console wiring parser→confirm BR-B1→filedrop; stand-in for the TuiPlugin, reused by the harness). **13 bun unit tests
      pass.** **TUI injection verification (user-requested):** `test/e2e/{pty_harness,run_inject_e2e}.py` — a stdlib-`pty` keystroke-
      injection harness drives the console in a real pseudo-terminal and asserts parse→confirm→token+append (incl. destructive
      requires CONFIRM, malformed rejected, read no-write). **PASS (8/8 checks).** The SAME harness drives the real `bun dev` opencode
      TUI on the user's machine (full-TUI e2e = automated, not manual). **Remaining:** real opencode TuiPlugin wiring (reuses
      parser/filedrop verbatim) + panels/modal/toast via TuiPlugin + the steer custom tool; Phase 2 full command set; Phase 3
      compile-time tool removal (registry.ts) + rebrand; Phase 4 cross-language contract test + run the injection e2e against `bun dev`.
    - **`/code-review` (high effort, 3 finder agents + verify) 2026-05-30 — 9 findings, fixed & committed (`a685781`, `61ea2ff`):**
      #1 `/answer` now validates the question id vs open agent_questions (unknown→rejected, not a false "applied"+orphaned answer);
      #2 parser drops the `directive clear` two-word case (hijacked a directive whose text starts with "clear") → `/directive-clear`
      alias; #3 `intArg` strict `/^\d+$/` (parseInt accepted "3abc"/"3.9"); #5 extracted the confirm/dispatch state machine to a
      SHARED `src/dispatch.ts` (stub + real TuiPlugin reuse it; PTY-verified logic can't drift) + 7 unit tests; #6 `readEvents`
      positioned read of only [offset,size) (was whole-file each poll); #7 `/stop` rejects a long stop at/above market (immediate-exit
      fat-finger); #8 symbol must start with a letter; #4 documented (events.jsonl append-only, consumer dedups). Also fixed a
      `.gitignore` footgun: `steering/`→`/steering/` so it doesn't shadow `src/agent/steering/`. **TS 20 bun tests + PTY e2e PASS;
      Python full suite 273 pass.** Unit B commits on `feat/steering-core`: 4f68c64, a685781, 61ea2ff.
    - [x] **Phase 1 FINISH — `steer` opencode plugin (NL path) committed (`b02bf4d`).** Read the opencode plugin SDK from the clone:
      a plugin contributes a custom tool via `Hooks.tool: {steer: tool({description, args: zod, execute(args, ctx)})}` and
      **`ctx.ask(...)` is opencode's core-enforced human-permission prompt** → confirm integrity for the NL path (model proposes
      `steer({command})`; tool parses deterministically via src/parser; mutating cmd → `ctx.ask` human confirm (model can't bypass);
      on approval → token-attached write via src/filedrop; reads return snapshot). `src/plugin.ts` written against the real SDK
      (tool()/ToolContext.ask) + `README.md` (load/run/verify + OpenAI-auth/never-Claude-sub constraint + roadmap). **Cannot build
      opencode here (no make) → plugin verified LIVE by the user** (bun dev + PTY injection harness); reused parser/filedrop are
      unit-tested (20 bun tests). **Reframed remaining work:** dedicated TUI panels (positions/orders/pending/event-feed via TuiPlugin)
      + pure-keystroke LLM-bypass path = **Phase 2**; compile-time tool removal (registry.ts) + rebrand = **Phase 3**; cross-language
      contract test + injection e2e vs `bun dev` = **Phase 4**. 4 Unit B commits (4f68c64, a685781, 61ea2ff, b02bf4d).
    - **Live debugging + MCP redesign (2026-05-30):** Plugin loaded only after fixing (a) default-export must be `{server}`
      (e0cdd0a), then steer (b) **auto-confirmed** — opencode `Permission.ask` only prompts on a matching config rule; my inner
      `ctx.ask` key didn't match (a4480d6), and (c) plugin tools are NOT auto-gated (only MCP tools are, tools.ts:135) so the tool
      must self-ask — restored with key "steer" matching `permission:{steer:"ask"}` (105aabe). **User asked: would MCP simplify? →
      YES, redesigned (a5ba10f):** `steer`/`steer_read` now an **MCP stdio server** (`src/mcp-server.ts` + tested `steer-handler.ts`,
      @modelcontextprotocol/sdk@1.29+zod@4 pinned). opencode **auto-gates MCP tools** (`ctx.ask({permission:"autostock_steer"})`
      before execute) → **confirm enforced by opencode CORE, not our code** — removes the self-ask failure mode + the 3 plugin
      gotchas (export shape / SDK resolution / self-ask). config: `mcp:{autostock:{type:local,command:[bun,run,mcp-server.ts],
      environment:{STEERING_DIR,STEERING_OPERATOR_TOKEN}}}` + `permission:{"autostock_steer":"ask","autostock_steer_read":"allow"}`.
      Removed the steer plugin (plugin.ts); plugin reserved for Phase-2 TUI panels. 26 bun tests pass; live auto-gate verified by user.
    - **Fork vendored + Phase 3a lockdown (2026-05-30):** opencode fork = submodule `operator-console/cli` →
      `github.com/inventor71/autostock-cli` (user's rename of oc_spike), pinned (autostock 2e42789 → re-pinned to fork 5e76156).
      Shipped `opencode.json` IN the fork (force-added — opencode gitignores it): mcp `autostock`→`../src/mcp-server.ts` +
      **Phase 3a tool lockdown via config default-deny**: `permission:{"*":"deny", read/glob/grep/list/lsp:"allow",
      autostock_steer:"ask", autostock_steer_read:"allow"}`. Realizes BR-B4 (operator LLM = reads + steer only; edit/write/bash/
      task/webfetch denied by opencode CORE gate; denying `task` moots #5894 subagent bypass) WITHOUT risky unverifiable
      registry.ts surgery. **Deferred (need fork build = user's machine):** true compile-time removal in registry.ts (belt-and-
      suspenders) + binary rebrand. **per-verb confirm:** per-verb MCP tools in our mcp-server.ts (verifiable, no fork edit) give
      per-command "always" separation (destructive-always still needs a gate source edit). User verifies lockdown live.
    - **Phase 2 STARTED (2026-05-30):** opencode UI = solid-js TuiPlugins registering `sidebar_content` slots (template
      feature-plugins/sidebar/todo.tsx, registered in plugin/internal.ts); TuiPluginApi gives slots / ui.toast / ui.DialogConfirm /
      keymap.registerLayer. **Slice 1 done (fork a4bb4b7, re-pinned):** feature-plugins/sidebar/autostock.tsx — reads
      STEERING_DIR/snapshot.json (Unit A's published read-view) every 1.5s, shows run-state/market/positions(+locked)/pending count;
      read-only, registered in internal.ts. Typecheck clean (tsgo, 0 errors). **Remaining Phase 2 slices:** (2) event-feed — tail
      events.jsonl → ui.toast on fill/pending/agent_question; (3) keystroke LLM-bypass path — keymap.registerLayer → deterministic
      parse (reuse parser) → ui.DialogConfirm (per-verb, can force destructive re-confirm) → file-drop write (reuse filedrop). Slice 3
      ALSO solves the deferred per-verb/destructive-always confirm (our code owns the modal, not opencode's MCP auto-gate).
## New Feature Track: Steering Console Redesign (F4)
- **Started**: 2026-05-29. **Picked up / resumed**: 2026-05-30. **Stage**: CONSTRUCTION → Code Generation (Unit B).
- **Supersedes F2 front-end** (prompt_toolkit console replaced). Keeps F2's daemon-side safety model but
  reimplemented cleanly. Locked decisions (F4 Q1–Q9 + Clarif-1/2) live in the project memory
  `steering-console-redesign.md` / `f4-steering-runtime-wiring.md` (F4 inception requirements doc was not
  committed to the repo — decisions are authoritative in memory). **Design = APPROVED.**
- **Worktree**: `.claude/worktrees/steering-core`, branch `feat/steering-core`.
- **Two units**:
  - **Unit A — steering-core** (Python daemon side, `src/agent/steering/`): file-drop JSONL command channel +
    single serialized CommandBus + TurnCoordinator + SteeringState + executor gate + privilege-separation hook.
    Opt-in via `main.py --mode agent --steering` (all paths guarded `if self.steering is not None`; default
    `--mode agent` unaffected). **STATUS: COMPLETE** — codegen Step 1–10 done; suite **273 tests green**.
  - **Unit B — operator-console** (opencode hard-fork, submodule `operator-console/cli` + `operator-console/src`):
    trader-rebranded opencode; talks to the daemon ONLY via the repo-root `steering/` channel; no order authority
    (proposes → human confirm → daemon `RiskManager→Broker` gate). Auth: console LLM = non-Anthropic (OpenAI OAuth);
    🚫 never the Claude subscription in opencode.
- **Unit B roadmap (README.md)**:
  - **Phase 1 — DONE**: deterministic core (`src/parser.ts`/`filedrop.ts`/`dispatch.ts`) + PTY injection harness +
    `steer`/`steer_read` MCP server (confirm = opencode core auto-gate). Committed lockdown `opencode.json`
    (`"*":"deny"` + allowlist) + `verify-lockdown.ts`.
  - **Phase 2 — IN PROGRESS**: slice 1 (autostock sidebar panel: run-state/positions/pending) DONE.
    **Remaining**: sidebar/orders + event-feed (tail `steering/events.jsonl`); pure-keystroke LLM-bypass command
    path (TUI input → `dispatch.ts` Dispatcher, no LLM).
  - **Phase 3 — TODO** (this pickup's target): compile-time removal of side-effect tools in
    `packages/opencode/src/tool/registry.ts` builtin (shell/edit/write/task/fetch/patch/search) so they are never
    registered (defense-in-depth atop the permission default-deny → opencode permission bugs structurally moot);
    extend `verify-lockdown.ts` to assert ABSENCE (not just deny); pin the fork baseline + rebrand.
  - **Phase 4 — DEFERRED** (beyond this pickup): cross-language contract test (TS schema ↔ Unit A pydantic golden
    samples) + injection e2e vs `bun dev`.
- **Code Generation plan**: `aidlc-docs/construction/plans/steering-console-redesign-code-generation-plan.md`.
- **Extension Configuration (F4)**: project default — Security Baseline Enabled (NFR-1 privilege separation is the
  headline: operator command authority structurally unreachable from advisor agent sessions; SECURITY-11/03/15
  applicable). Property-Based Testing N/A for the TS console phases (deterministic parser already example-tested).
- **Stage Progress (F4)**:
  - [x] Workspace/Reverse-Eng/Requirements/Planning/Design — reused/approved (see memory).
  - [x] Unit A Code Generation — COMPLETE (273 green).
  - [~] Unit B Code Generation — Phase 1 done; **Phase 2 DONE — NL-only** (Step 1 사이드바 확장 유지;
        Step 2 키스트로크 LLM-bypass는 구현·라이브검증까지 했으나 **제품 결정으로 제거** — 아래 NL-only 참고);
        **Phase 3 (Step 3–5) DONE** (2026-05-30):
        registry 락다운 필터(opt-in `AUTOSTOCK_LOCKDOWN=on`, 콘솔 런치 기본 ON), 2-레이어 검증(verify-lockdown
        PASS + registry 부재 테스트 16 그린), baseline 핀(opencode v1.15.12) + README.
  - [x] **Phase 4 (크로스랭귀지 컨트랙트) DONE** (2026-05-30): 골든 `operator-console/contract/contract.json`
        (pydantic 생성) 양방향 핀 — Python `tests/test_steering_contract.py`(4) + TS `test/contract.test.ts`(5) +
        `schema.ts` 망라성 타입체크. 드리프트 음성검증 통과. Python 273→**277 그린**, 콘솔 own **24 그린**.
  - [x] Build and Test — bun tests + tsc(schema/registry) + verify-lockdown PASS + python no-regression(277). **F4 Unit B 완료.**
  - **Note**: 부모 repo는 서브모듈 `operator-console/cli` 변경분(registry.ts/package.json/verify-lockdown/
        registry.test/사이드바/sidebar.tsx/index.tsx)을 아직 서브모듈에 커밋+재핀하지 않음. 머신-로컬 `.opencode/opencode.jsonc`는 커밋 제외.
  - **사이드바 가독성 (라이브 피드백 2026-05-30):** events가 raw JSON이라 안 읽힘 → kind별 사람-친화 포맷(시각+글리프)
        + `wrapMode="word"`로 폭 안에서 전체 표시(잘림 제거). 폭은 `AUTOSTOCK_SIDEBAR_WIDTH` env knob(기본 42,
        24–120)로 조절 가능(sidebar.tsx+index.tsx). tsgo 0 errors.
- **제품 결정 — NL-only (2026-05-30):** 콘솔 명령 경로를 **자연어(MCP `autostock_steer`)** 단일 경로로 확정.
  한 번 만들었던 모델-비경유 키스트로크 경로(`tui-plugin.ts`/`dispatch.ts`/`console-stub.ts`/PTY e2e + tui.json
  등록)는 **제거**. 근거: 두 경로가 같은 confirm+게이트라 안전성 동일, 둘째 경로 값은 타이핑 절약뿐 → 깔끔함 우선.
  결정성은 MCP 경로 내부 `parser.ts`(검증기)에 유지. 트레이드오프: steering이 콘솔 LLM(OpenAI) 가용성에 의존
  (break-glass=Alpaca UI→reconcile). 안전 아키텍처(confirm/RiskManager/Broker/Unit A)는 불변. F4 Q4=B("LLM은
  제안만")와 일관 — 제거한 건 로드맵 *추가분*이지 락된 결정이 아님.
- **Deferred feature idea (F-future): 사이드바 마우스 드래그 리사이즈** — opencode 사이드바는 폭 고정(42, 이제 env override).
  마우스 드래그 핸들/동적 상태/재레이아웃이 필요해 별도 AI-DLC feature 트랙으로 분리(사용자 결정 2026-05-30).

## New Feature Track: Console-native Launcher & Rebrand (F5)
- **Started**: 2026-05-30. **Stage**: INCEPTION → Requirements Analysis (Standard depth), awaiting answers at the gate.
- **Goal (user)**: Make the F4 operator console more convenient & stock-native. Three musts: (1) start directly in the
  sidebar-visible view (currently the opencode home/splash with the animated "opencode" logo + "Ask anything..." box shows
  first); (2) rebrand the logo "opencode" → "autostock"; (3) replace the entry point — instead of `cd operator-console/cli &&
  bun dev`, ship a `claude`-like binary/single command, manage the daemon via systemd (auto-start if down, attach if already
  running), and improve error handling so a failed tool launch never silently exits.
- **Built on F4** (DONE/merged engine + opencode hard-fork console at `operator-console/`). Brownfield; Workspace Detection &
  Reverse Engineering reused.
- **Grounding (read 2026-05-30):** logo glyphs `operator-console/cli/packages/opencode/src/cli/logo.ts` (+ `component/logo.tsx`
  shimmer render); home screen `feature-plugins/home/`; sidebar `feature-plugins/sidebar/autostock.tsx` (toggle `<leader>b`);
  launch `cd operator-console/cli && bun dev`; daemon `python main.py --mode agent --steering` (repo-root `steering/` channel,
  shared token). **Platform = WSL2** → systemd may be disabled (flagged for item 3, drives Q4 portable-fallback option).
- **Extensions (F5)**: default to project config (Security Baseline Enabled — esp. SECURITY-03 no-secret-in-logs given new
  diagnostics could leak the operator token, SECURITY-11 privilege separation unchanged, SECURITY-15 fail-closed startup;
  PBT mostly N/A for launcher/TS UX) — confirming via Q8.
- **Stage Progress (F5)**:
  - [x] Workspace Detection — reused (brownfield, existing project).
  - [x] Reverse Engineering — reused (artifacts already exist).
  - [x] Requirements Analysis — **COMPLETE** 2026-05-30 (awaiting approval). Answers (all recommended defaults, no contradictions):
        **Q1=A** (skip home/splash → session view + autostock sidebar default-on), **Q2=B** (rebrand ASCII logo + ALL visible
        "opencode" strings), **Q3=A** (systemd manages the Python trading daemon; console = foreground TUI that attaches, auto-starts
        daemon if down), **Q4=A** (systemd **user** service; user note: re-decide if systemd activation breaks), **Q5=A** (`autostock`
        thin launcher installed on PATH, bun runtime — not a compiled binary), **Q6=B** (preflight + runtime disconnect banner; no
        silent exit), **Q7=A** (token value never printed/logged, masked), **Q8=A** (project-default extensions). Requirements doc:
        `aidlc-docs/inception/requirements/console-native-launcher.md`. **Env verified:** systemd IS live in this WSL2 (PID1=systemd,
        `systemctl --user`=running, wsl.conf systemd=true, bun 1.3.14) → Q4=A premise holds, contingency not triggered.
  - [x] User Stories — **SKIP** (single-operator tool; workflows captured as FR-1..6; consistent with F2/F3/F4).
  - [x] Workflow Planning — **COMPLETE** 2026-05-30 (awaiting approval). Plan:
        `aidlc-docs/inception/plans/console-native-launcher-execution-plan.md`. Risk **Medium**. Application Design SKIP (→Functional
        Design), Units Generation SKIP, Infrastructure Design SKIP (systemd unit folded into Functional/NFR Design). **Single unit
        `console-native-launcher`**, internal sequence S1 rebrand → S2 sidebar-first → S3 preflight → S4 systemd-user daemon
        auto-start/attach → S5 `autostock` thin launcher+install → S6 runtime-disconnect banner → S7 tests+submodule re-pin+live
        verify. Per-unit Functional Design (light) / NFR Requirements (minimal, 0 new runtime deps) / NFR Design / Code Generation /
        Build&Test = EXECUTE. worktree-isolated. 2-unit alternative (console-ux / launcher-ops) noted, not recommended.
  - **CONSTRUCTION — Unit `console-native-launcher`:**
    - [~] Functional Design — questions posed 2026-05-30 `construction/console-native-launcher/functional-design/functional-design-questions.md`
          (Q1 logo wordmark layout [1-line/2-line-stack/2-segment, previews] · Q2 systemd policy: auto-restart+boot-enable(linger) ·
          Q3 daemon lifecycle on console exit · Q4 install PATH target). Grounded: home plugin `feature-plugins/home/` (tips/footer in
          internal.ts), sidebar `autostock.tsx` `sidebar_content()` slot, daemon `main.py --steering` loads root `.env` token.
    - [x] Functional Design — **COMPLETE** 2026-05-30 (awaiting approval). Answers (all recommended): **Q1=B** (logo = 2-line stack
          "auto"/"stock", shimmer kept), **Q2=A** (systemd user: Restart=on-failure + boot/login enable + linger), **Q3=A** (daemon
          detached, survives console exit), **Q4=A** (install `~/.local/bin/autostock`). Artifacts in
          `construction/console-native-launcher/functional-design/`: domain-entities.md (E1 PreflightCheck/E2 PreflightReport/E3
          DaemonService/E4 DaemonHealth[snapshot.json freshness]/E5 LauncherConfig[token in-memory only]/E6 RuntimeHealthSignal/E7
          BrandSurface), business-logic-model.md (launch seq env→preflight→ensure_running→console→watch; token-match constant-time
          boolean; mcp_path guards the relative-path/Module-not-found regression), business-rules.md (BR-1 fail-closed/no-silent-exit,
          BR-2 wedged, BR-3/9 no-double-start, BR-4 console-independent daemon, BR-5 systemd policy, BR-6 token-never-printed, BR-10/11
          privilege unchanged, BR-12 contract unchanged, BR-13 no-regression, BR-7 sidebar-first, BR-8 banner, BR-14 rebrand scope,
          BR-15 install path), frontend-components.md (FC-1..5). Python daemon code-change target = 0.
    - [x] Functional Design — **APPROVED** 2026-05-30 ("승인후 다음단계").
    - [x] NFR Requirements — **COMPLETE (minimal)** 2026-05-30 (awaiting approval). Artifacts in
          `construction/console-native-launcher/nfr-requirements/`: nfr-requirements.md + tech-stack-decisions.md. **Conclusion: 0 new
          runtime deps.** Launcher = Bun/TS script + thin shell shim on `~/.local/bin/autostock` (reuses `operator-console/src/
          filedrop.ts`+`schema.ts`); systemd via `systemctl --user`/`loginctl enable-linger` + generated user unit
          (`~/.config/systemd/user/autostock-daemon.service`, ExecStart=venv python `main.py --mode agent --steering`,
          EnvironmentFile=root .env); preflight TS reusing filedrop; rebrand/sidebar/banner = fork TS/SolidJS edits; idempotent install
          script. No new question round. Deferred to NFR Design: launcher concurrency (health-wait poll × systemctl), exact unit
          fields/install order, preflight module boundary + constant-time token compare placement, banner injection. health-wait consts
          (window 15s / timeout 20s / poll 0.5s) to confirm in Code Gen.
    - **`/critic` adversarial review (isolated subagent) 2026-05-30 — 6 findings, all cross-verified valid vs main code; engineering
          refinements applied to FD+tech-stack docs:** #1 [MED] snapshot health=mtime but `publish_snapshot` queues `_build` on the
          SINGLE bus worker (runtime.py:125) behind executor `_funnel(timeout=180)` (agent.py:58) → mtime lags → health_window=15s
          false-"wedged" → **BR-2.1** (window ≥30-45s + published_at/2-consecutive-fresh, not bare mtime). #2 [MED] `"opencode"` is a
          load-bearing provider-id (`item.id !== "opencode"` tips.tsx:44, sidebar/footer.tsx:12) + capitalized titles "OpenCode"/"OC |"
          (app.tsx:459/466/471/476) → **BR-14.1** (exclude provider-id literal) + **BR-14.2** (add caps titles to visible_strings).
          #3 [MED] home is the default ROUTE not a skippable splash (app.tsx:458; session nav only --session/-c/-fork) → **BR-7.1**
          (home-skip = auto-nav-to-session OR sidebar slot on home route; Code-Gen spike, default = sidebar-on-home). #4 systemd unit
          MUST set `WorkingDirectory={AUTOSTOCK_ROOT}`(+EnvironmentFile) else main.py:366 load_dotenv (CWD-relative) misses .env →
          runtime.py:47 random token → console mismatch → all commands rejected; `--steering` no-TTY (while-True loop) → Type=simple OK,
          "0 Python changes" holds → **tech-stack §2 hardened**. #5 sidebar default-on = auto only in WIDE terminals, hidden narrow/child
          (session/index.tsx:236-241) → **BR-7.2** qualified. #6 ONE canonical token source compared AND injected (root .env), warn on
          cli/.env drift → **tech-stack §3 hardened**. Sound (not churned): shimmer renderer data-driven (logo.tsx:299),
          atomic_write_text bumps mtime (jsonl.py:28-31), systemd start idempotent (**BR-9.1**). **Policy fork → user:**
          `critic-clarification-questions.md` Q1 = submodule `operator-console/cli` re-pin ownership.
    - **Re-pin ownership = A** (answered 2026-05-30): F5 owns submodule commit + push to autostock-cli remote + parent re-pin
          (at Code-Gen S7). Caveat: if remote push auth unavailable in env → surface + fall back to local commit + parent re-pin.
          **Gate: 2-option NFR Requirements (hardened) — awaiting approval.**
    - [x] NFR Requirements — **APPROVED** 2026-05-30 ("승인할게").
    - [x] NFR Design — **COMPLETE** 2026-05-30 (awaiting approval). Artifacts in
          `construction/console-native-launcher/nfr-design/`: nfr-design-patterns.md + logical-components.md. **Patterns:** P1
          fail-closed orchestration (exit codes 0/10/11/12/13, no undiagnosed path); P2 health=snapshot freshness — `health_window=45s`
          (tuned to bus worst-case, NOT 5s cadence) / `healthwait_timeout=60s` / `poll=1s`, healthy = `published_at` advance OR 2
          consecutive fresh (no bare-mtime) [critic #1]; P3 systemd user unit `Type=simple` + `WorkingDirectory={AUTOSTOCK_ROOT}` +
          `EnvironmentFile` + `Restart=on-failure`+enable+linger, ensure_installed/ensure_running idempotent [critic #4]; P4 canonical
          token = root .env compared AND injected, warn on cli/.env drift, never printed [critic #6]; P5 preflight pure checks
          (token_canonical/steering_dir/mcp_path blocking); P6 home-skip = render autostock sidebar slot on `routes/home.tsx` (input
          flow preserved; Code-Gen spike) [critic #3]; P7 runtime banner on 1.5s poll; P8 rebrand excludes provider-id literal, includes
          caps titles [critic #2]. **logical-components:** new `operator-console/launcher/` (cli/config/preflight/daemon/unit-template/
          install) + `~/.local/bin/autostock` shim, reuses `src/filedrop.ts`/`schema.ts` (0 new deps); fork edits enumerated; Python
          0-change; verification items 1-6 + test strategy. **Gate: 2-option NFR Design — awaiting approval.**
    - [x] NFR Design — **APPROVED** 2026-05-30 ("승인").
    - [x] Infrastructure Design — **SKIP** (local launcher/daemon; systemd unit folded into Functional/NFR Design).
    - [~] Code Generation **Part 1 (plan)** — created 2026-05-30, **awaiting approval to enter Part 2**. Plan:
          `construction/plans/console-native-launcher-code-generation-plan.md` (Step 0 worktree → 1 launcher core [config/preflight/
          unit-template]+tests → 2 daemon.ts systemd+health-wait+tests → 3 cli.ts orchestration+install shim → 4 rebrand
          [logo 2-line/titles/provider-id-exclude] → 5 home sidebar slot [critic #3 spike] → 6 runtime banner → 7 tests+live verify
          [items 1-6]+submodule re-pin=A push). 0 new runtime deps; Python 0-change. On approval Part 2's first action = worktree off
          `main`; then S0-S7 autonomously, stopping only for live verification (fork build = user machine) + remote push auth. No code/worktree yet.
    - **`/critic` round 2 (code-gen plan + NFR design) 2026-05-30 — 6 findings, all cross-verified valid; engineering refinements
          applied to plan + nfr-design + business-rules:** #1 [HIGH] cli.ts exec-handoff (NO launcher-side watch; disconnect-watch lives
          in console P7) — "launchConsole→watch" was a TTY-contention contradiction → P1/Step3 fixed. #2 [HIGH] Step3 token-only inject
          → MCP silent-fail; opencode.jsonc:20 needs `{env:AUTOSTOCK_ROOT}` abs path + cwd=operator-console/cli → inject
          AUTOSTOCK_ROOT+STEERING_DIR+token + correct cwd + post-launch `autostock_steer` assertion (P4/Step3). #3 [MED] systemd
          EnvironmentFile≠dotenv (.env clean now, latent) → DROP EnvironmentFile, WorkingDirectory+load_dotenv authoritative (P3/Step2).
          #4 [MED] worktree skips submodule checkout + detached-HEAD risk → Step0 `submodule update --init` + submodule real branch;
          Step7 gitlink commit in worktree. #6 [LOW] published_at naive-local → parse-as-local in JS (mirror autostock.tsx:92) + test (P2).
          **#5 [HIGH→POLICY FORK]:** sidebar-on-home is layout surgery, not slot-registration (home.tsx:74-89 centered column, no
          side-region; `sidebar_content` only at session/sidebar.tsx:92, session-gated session/index.tsx:236). Round-1 "less invasive"
          premise FLIPPED; **original Q1=A "바로 세션 뷰로" aligns with auto-nav-to-session.** Re-scoped BR-7.1/P6/Step5 to 2 options:
          **A** home row-layout surgery vs **B (recommend)** auto-nav to session route (`-c`/synthetic) reusing the working sidebar path.
          → `critic2-clarification-questions.md` Q1 — **answered = B** (auto-nav to session, matches Q1=A intent). Step 5 finalized to B.
    - [x] Code Generation **Part 1 (plan)** — **APPROVED** 2026-05-30 ("B로 하고 승인"). Entering Part 2 (autonomous).
    - [~] Code Generation **Part 2 (build)** — IN PROGRESS 2026-05-30. **Steps 0-3 DONE + committed** (worktree
          `.claude/worktrees/console-native-launcher`, branch `feat/console-native-launcher`; submodule on branch `feat/console-native-launcher`):
          **Step 0** worktree + submodule init (confirmed empty in fresh worktree = critic2 #4) + submodule real branch.
          **Steps 1-3** `operator-console/launcher/` {config,preflight,unit-template,daemon,cli,install}.ts — commit `8e51aba`. 0 new deps
          (reuses src/filedrop.ts). All critic2 fixes in code: #1 exec-handoff no launcher-watch, #2 full console env (AUTOSTOCK_ROOT+
          STEERING_DIR+token)+cwd, #3 no EnvironmentFile, #6 naive-local published_at; health-wait window 45s/timeout 60s/advance-or-2-fresh
          (critic #1); exit codes 0/10/11/12/13 (no silent exit). **20 launcher tests + full console suite 45 green; bun build clean.**
          **Step 4a** terminal titles OpenCode→autostock / OC|→AS| — submodule commit `241351a` (BR-14.2; provider-id literal untouched BR-14.1).
          **Remaining (render-dependent → user-machine build+live loop):** Step 4 logo glyph art (2-line auto/stock — visual-iterative) +
          broader visible-string rebrand; Step 5 session-first live behavior (`-c` wired in cli.ts, verify lands in session+sidebar);
          Step 6 runtime-disconnect banner in autostock.tsx; Step 7 live verify (items 1-6) + submodule push (autostock-cli) + parent re-pin (re-pin=A).
          NOT pushed/re-pinned yet (fork edits incomplete). Daemon Python code unchanged (0).
    - **LIVE VERIFICATION 2026-05-30 (user: "직접 라이브 검증… 장 안열려 안전… main의 .env 사용")** — read-only against the MAIN
          checkout's REAL running daemon (market closed, 0 side effects, 0 LLM). PASSED: config/token(present,unshown)/consoleEnv 4-key
          inject (critic2 #2); preflight all green; healthWait healthy ~1s vs the real 5s daemon (critic #1 no false-wedged); unit render
          WorkingDirectory+venv+no-EnvironmentFile (critic #3/#4). **LIVE-VERIFY BUG FOUND & FIXED (commit `8cd1c51`):** the running
          daemon was MANUAL (not systemd) → `is-active`=inactive → ensureRunning would `systemctl start` a 2ND instance over the same
          channel/broker. True attach signal = fresh ADVANCING snapshot, not systemd state. Hardened: ensureRunning **health-first**
          (fresh→advance-probe 8s→attach, never start; start only if not live); healthWait now REQUIRES advance (dropped weak 2-fresh →
          a dead-<window daemon's frozen-recent snapshot must not read healthy). Live-verified with a throw-on-start runner: attached ~4s,
          0 systemctl start. Tests: frozen-fresh→wedged + attach/down/failed. **Console own suite 46 pass/0 fail** (submodule fork tests
          excluded — not runnable here). Launcher core (Steps 0-3 + hardening) = LIVE-VERIFIED. Commits on `feat/console-native-launcher`:
          `8e51aba` (1-3), `8cd1c51` (health-first); submodule `241351a` (titles).
    - **`/critic` round 3 (launcher CODE) 2026-05-30 — 4 findings, all fixed + live-verified (commit `cc99630`):** #1 [HIGH] the
          round-2 health-first fix STILL double-started — the 8s advance probe FELL THROUGH to `systemctl start` when a live-but-busy
          daemon's 5s snapshot job is delayed past 8s (APScheduler max_instances=1 starved by a minutes-long premarket/intraday LLM turn).
          FIXED: **fresh ⇒ ATTACH, never start** (advance probe informational only; missing advance ≠ dead) + race-guard re-check before
          start; BR-3.1 corrected. Trade-off: a daemon dead <45s isn't auto-restarted that invocation → console banner surfaces it (safe
          lesser evil). #2 [MED] ensureInstalled skip-if-exists → stale unit; FIXED self-healing rewrite+daemon-reload on drift. #3 [MED]
          linger failure silently swallowed; FIXED warn+guard empty $USER. #4 [LOW] runner no timeout; FIXED RUN_TIMEOUT_MS.
          Critic-verified SOUND: microsecond published_at non-NaN (local), token never leaked, `bun run dev -- -c` forwards, cfg assigned,
          stderr-not-stdout. Tests +5 (frozen/busy→no-start, stale→rewrite, identical→no-op, microsecond parse, token-not-in-output):
          **26 launcher + 51 console-own green; bun build clean.** **Live re-verified vs REAL daemon: advancing AND frozen/busy both
          attach with ZERO systemctl start.** Launcher core commits: `8e51aba`, `8cd1c51`, `cc99630`.
    - **Fork UI written 2026-05-30 (user: "①로 남은 포크 UI 마저 작성")** — submodule `feat/console-native-launcher`:
          **S4c logo** `cli/logo.ts` → 2-line stacked "auto"/"stock" half-block wordmark (8 rows in `left`, empty `right`, block
          glyphs only; renderer data-driven so no logo.tsx change). **S6 banner** `sidebar/autostock.tsx` → panel now ALWAYS renders
          (was `Show(snap)` → blank exactly when disconnected) + ⚠ banner when STEERING_DIR unset / snapshot missing / published_at
          stale >30s (naive-local parse, no secrets). **S5 session-first** = launcher `bun run dev -- -c` (cli.ts). Submodule commit
          `ea9a885` (+ `241351a` titles). JSX tag-balance checked (box 3/3, Show 6/6). **Not buildable here (fork TUI needs the build
          toolchain) → logo visual tweak + tsgo + behavior = user-machine live loop.** NOT pushed/re-pinned (re-pin=A deferred to post-verify).
    - **User visual verify 2026-05-30** — main logo OK; found the Ctrl+C **exit screen clipped** the 2-line logo to 4 rows
          (`routes/session/index.tsx` hardcoded `logo[0..3]`) → fixed to spread all `UI.logo()` lines (commit `3e68af9`). tsgo clean.
    - **Brand pass 2026-05-30** (submodule `05df2ce` + parent `f2616bd`): resume hints → `autostock -s <id>` (session/index + run/splash),
          notification DEFAULT_TITLE → autostock (attention.ts), non-TTY `wordmark` → "autostock" (ui.ts); **launcher forwards args**
          (`autostock -s ses_x` resumes, bare → `-c`). Left functional: config paths/theme-id/provider-ids/MCP clientInfo/binary spawns.
          Remaining coding-oriented copy (home prompt placeholders + tips-view.tsx) **carved out to F7** (user decision).
    - **Step 7 DONE 2026-05-30:** final tests **51 console-own + 26 launcher green**; fork branch **pushed to autostock-cli origin**
          (SSH OK, `feat/console-native-launcher`); parent **gitlink re-pinned** to submodule `05df2ce` (commit `da724cf`). re-pin=A complete.
    - **F5 status: DONE & MERGED TO MAIN 2026-05-30** (user: "머지해"). docs commit `7f21bd1`; merge commit `aaf01e2` (--no-ff);
          main submodule updated to `05df2ce`; submodule fork pushed to `autostock-cli` origin. Verified on main: launcher files present,
          logo.ts = autostock, 26 launcher tests green, working tree clean. **F5 COMPLETE.** F7 (trading-native copy/tips) carved out,
          resumable via /ai-dlc-resume.
          **Usage:** one-time `bun run operator-console/launcher/install.ts` (installs `~/.local/bin/autostock` + systemd user unit
          `autostock-daemon.service` w/ Restart+linger); then `autostock` (auto-start/attach daemon → console+sidebar+MCP) or
          `autostock -s <id>`. NOTE: a manual daemon (PID 1188466, non-systemd) was running — `autostock` health-first ATTACHES to it;
          to switch to systemd-managed, stop the manual one first.
    - **Post-merge live fixes 2026-05-30:** (a) name collision — pyproject `autostock`→`autostockd` + install.ts shadow-check
          (commit `187877c`); (b) broken `.venv` — resolvePython prefers $VIRTUAL_ENV + validates deps, self-healing unit (commit
          `5559178`). Daemon then started agent+steering correctly; console live-verified (MCP autostock Connected, sidebar live).
    - **Option ② (sidebar-first, clean session) 2026-05-30 (user: "2번으로 가자")** — `-c` had resumed the last (stale "hello")
          session. Fix: launcher drops the default `-c` (bare `autostock` → fresh home; `autostock -s <id>` still resumes), and the
          autostock sidebar now renders on the **home route** (home.tsx row layout + new `home_sidebar` slot, wide-gated BR-7.2;
          autostock.tsx registers View into it). Fresh launch = autostock logo + prompt + live sidebar, no stale chat. Submodule commit
          `21ac3bc` (pushed to autostock-cli); tsgo clean + 26 launcher tests green. Parent re-pin + cli.ts committed to main.
    - **✅ F5 COMPLETE & CLOSED 2026-05-30 (user: "잘 뜨네. 마무리해줘").** Live-verified end-to-end: `autostock` (one command) →
          systemd daemon (agent+steering) auto-start/attach → opencode console (MCP autostock Connected) → fresh home + live trading
          sidebar (option ②). All three asks delivered: (1) sidebar-first start, (2) autostock rebrand (logo/titles/resume/wordmark),
          (3) `autostock` binary + systemd daemon mgmt + fail-closed error handling. On `main` (merge `aaf01e2` + post-merge `187877c`/
          `5559178`/`d8b407a`); fork submodule `21ac3bc` on `feat/console-native-launcher` pushed to autostock-cli. Construction Build&Test
          satisfied by the live verification + 26 launcher / console-own test runs + tsgo. Redundant worktree removed. **F7** (trading-native
          copy/tips) remains carved out + resumable. Project memory: `console-native-launcher.md`.

## New Feature Track: Console Sidebar Upgrade (F6)
- **Started**: 2026-05-30. **Stage**: INCEPTION → Requirements Analysis (Standard depth) — **COMPLETE, awaiting approval.**
- **Goal (user)**: Upgrade the F4 operator-console sidebar. Realizes the F4-deferred **mouse-drag resize** (state line ~748)
  + **visibility/readability** + migrate part of `scripts/monitor.sh`'s monitoring duties into the sidebar. ⚠ F5
  (console-native-launcher, now at NFR-Requirements gate) is concurrently editing the same files — coordinate.
- **Built on F4** (opencode hard-fork at `operator-console/`). Brownfield; Workspace Detection & Reverse Engineering reused.
- **Grounding (read 2026-05-30):** sidebar width `routes/session/sidebar.tsx:15` `sidebarWidth()` = static env read (fixed 42,
  `AUTOSTOCK_SIDEBAR_WIDTH` 24–120 override), code comment explicitly defers drag-resize → THIS track. Content panel
  `feature-plugins/sidebar/autostock.tsx` (run-state/market/positions/orders/pending/queued/events, snapshot.json+events.jsonl
  1.5s poll, read-only). Layout `routes/session/index.tsx:243` `contentWidth = width − sidebar − 4`. **OpenTUI exposes
  onMouseDown/onMouseDrag/onMouseDragEnd/onMouseDrop/onMouseMove/onMouseUp → drag-resize feasible.** monitor.sh = 4 tmux panes
  (decisions stream / status.py account dashboard / agent log tail / turns+trades telemetry).
- **Extensions (F6)**: project default — Security Baseline Enabled (SECURITY-03 no-secret-in-logs for new diagnostics,
  SECURITY-11 privilege separation UNCHANGED, SECURITY-15 fail-closed display); PBT mostly N/A (TS UI).
- **Stage Progress (F6)**:
  - [x] Workspace Detection — reused (brownfield, existing project).
  - [x] Reverse Engineering — reused (artifacts already exist).
  - [x] Requirements Analysis — **COMPLETE** 2026-05-30 (awaiting approval). Question file:
        `inception/requirements/sidebar-upgrade-questions.md`; requirements: `inception/requirements/sidebar-upgrade.md`.
        **Answers (all recommended defaults):** **Q1=A+E** (sidebar gets account core metrics [equity/cash/day-PnL/cum-PnL]
        + closed round-trip summary [win-rate/realized-PnL]; **B/C/D = turn-telemetry / recent-decisions / agent-log-tail
        registered as on-demand slash/read commands, NOT sidebar-resident**), **Q2=A** (readability/style: section
        dividers, PnL color ±, number alignment, empty states — NOT default-on/width, which F5 owns), **Q3=A** (drag width
        PERSISTED across restarts; env = initial default only, saved > env > 42), **Q4=A** (independent worktree off `main`,
        reconcile/rebase at merge; exclude F5-owned default-on/rebrand from F6 scope), **Q5=A** (project-default extensions).
        **FR-1 drag-resize** (reactive width signal + handle + contentWidth re-layout + persistence), **FR-2/3** account &
        round-trip summary (prefer publish_snapshot field extension, no off-thread broker), **FR-4** deep monitoring as
        on-demand read commands (mechanism TBD in FD: opencode slash cmd vs read MCP tool), **FR-5** visibility/style.
        **Risk Low–Medium** (read-only UI; order path / privilege separation unchanged).
  - [x] Requirements Analysis — **APPROVED** 2026-05-30 ("계속 진행").
  - [x] User Stories — **SKIP** (single-operator tool; workflows captured as FR-1..5; consistent with F2/F3/F4/F5).
  - [x] Workflow Planning — **COMPLETE** 2026-05-30 (awaiting approval). Plan:
        `inception/plans/sidebar-upgrade-execution-plan.md`. Risk **Low–Medium** (read-only UI; order/steering/privilege
        path unchanged; largest change = static→reactive sidebar width + main re-layout [TS/SolidJS] + small Python snapshot
        payload extension). **Stage determination:** Application Design SKIP (→FD), Units Generation SKIP (single unit),
        Infrastructure Design SKIP (local TUI). **Single unit `console-sidebar-upgrade`**, internal sequence: S1 reactive
        width + drag-resize (sidebar.tsx + index.tsx contentWidth) → S2 width persistence (saved>env>42) → S3 account
        metrics + round-trip summary via publish_snapshot extension (runtime.py already calls get_portfolio_state on the
        worker → add equity/cash/open_pnl/position_count; round-trip via match_round_trips) → S4 readability/style →
        S5 on-demand read commands (FR-4, slash vs MCP read tool TBD in FD) → S6 tests + submodule re-pin + live verify.
        Per-unit FD / NFR-Req (minimal, 0 new runtime deps) / NFR-Design / Code Gen / Build&Test = EXECUTE. Base = worktree
        off `main`; F5-owned default-on/rebrand excluded from F6 scope (coordinate at merge). 2-unit alt noted, not recommended.
  - **CONSTRUCTION — Unit `console-sidebar-upgrade`:**
    - [x] Functional Design — **COMPLETE** 2026-05-30 (awaiting approval). FD questions all = recommended: **Q1=A**
          (drag width persisted to a console-only user state file, XDG `~/.local/state/autostock-console/ui.json`,
          saved>env>42), **Q2=A** (BOTH account [equity/cash/open_pnl/position_count] AND round-trip summary
          [closed_count/win_rate/realized_pnl] via `publish_snapshot` extension — account reuses the worker's existing
          get_portfolio_state, round-trip via `src/core/trades.py match_round_trips` + ET-date filter), **Q3=A** (FR-4 deep
          monitoring = `steer_read{view}` MCP tool extension reading daemon-published `steering/` read files for
          turns/decisions/log — read-only, contract boundary kept, F4 NL/MCP consistent), **Q4=A** (thin left-edge drag
          handle │ + onMouseDown/Drag/DragEnd, width=dims.width−e.x clamped, no keyboard alt). Grounded: sidebar renders
          right; OpenTUI MouseEvent has absolute x; steer_read already returns snapshot; runtime.publish_snapshot already on
          worker. Artifacts in `construction/console-sidebar-upgrade/functional-design/`: domain-entities.md (E1 SidebarWidthState
          /E2 AccountSummary/E3 RoundTripSummary/E4 MonitorView/E5 DragHandle), business-logic-model.md (BLM-1..6 reactive width
          + snapshot ext + steer_read{view} + data-flow), business-rules.md (BR-1..16), frontend-components.md (FC-1..5 + change
          surface table). Python daemon change = small (snapshot fields + monitor publisher + round-trip aggregator); order/
          steering/privilege path unchanged.
    - [x] Functional Design — **APPROVED** 2026-05-30 ("진행"). Construction running autonomously per
          [[feedback-autonomy-construction]] (NFR Req → NFR Design → Code Gen Part 1, stop before worktree).
    - [x] NFR Requirements — **COMPLETE (minimal)** 2026-05-30. Artifacts:
          `construction/console-sidebar-upgrade/nfr-requirements/{nfr-requirements,tech-stack-decisions}.md`. **Conclusion: 0
          new runtime deps** (TS: OpenTUI mouse events + stdlib fs + pinned MCP sdk/zod; Python: pydantic/loguru/APScheduler/
          alpaca + match_round_trips + add_seconds_job reused). NFR-P2 = no extra broker call (account from existing ps).
          PBT partial candidates: summarize_today_round_trips, clampWidth. No new question round. Verify items R1 (live drag in
          bun TUI), R2 (XDG ui.json I/O), R3 (steer_read{view} file return).
    - [x] NFR Design — **COMPLETE** 2026-05-30. Artifacts:
          `construction/console-sidebar-upgrade/nfr-design/{nfr-design-patterns,logical-components}.md`. P1 single-source
          reactive width (Sidebar.width + index.tsx contentWidth share one signal); P2 debounced atomic ui.json persist;
          P3 snapshot account/round_trip additive on the existing worker path (NFR-2, 0 extra broker call); P4 publish_monitor
          low-freq job (add_seconds_job ~5s) → atomic steering/monitor.json, steer_read{view} reads it (read-only, boundary
          kept); P5 fail-closed hide-when-absent (back-compat); P6 security (log-tail secret masking, read-only, fail-closed).
          Concurrency table: broker access stays daemon-worker single; console touches read-view/ui.json only. Infra SKIP.
    - [x] Infrastructure Design — **SKIP** (local TUI/daemon, no infra).
    - [~] Code Generation **Part 1 (plan)** — created 2026-05-30, **awaiting approval to enter Part 2**. Plan:
          `construction/plans/sidebar-upgrade-code-generation-plan.md` (Step 0 worktree → 1 Python round-trip aggregator +
          snapshot account/round_trip fields → 2 Python publish_monitor job → 3 TS steer_read{view} → 4 TS reactive width +
          XDG persist → 5 TS drag handle + re-layout → 6 TS sidebar account/perf + style → 7 build/test + submodule re-pin +
          live verify). 0 new deps. On approval, Part 2's FIRST action = `git worktree add … -b feat/console-sidebar-upgrade
          main`; no code/worktree yet. F5-owned default-on/rebrand NOT implemented. **Gate: approve Part 1 plan to start coding.**
    - [x] Code Generation **Part 1 (plan) — APPROVED** 2026-05-30 ("자율진행 시작").
    - [x] Code Generation **Part 2 (build) — COMPLETE** 2026-05-30 (worktree `.claude/worktrees/console-sidebar-upgrade`,
          branch `feat/console-sidebar-upgrade` off main; parent `e696630`, submodule `operator-console/cli` `82e009b` re-pinned;
          NOT pushed/merged). Code summary: `construction/console-sidebar-upgrade/code/code-summary.md`.
          **Daemon (Python):** broker `get_fills` port (base no-op + Alpaca reuses tested `_alpaca_fills` order-level fills —
          chosen over raw activities GET, simpler & 0-risk, adequate for the summary); `core/trades.summarize_today_round_trips`
          (match_round_trips + UTC→ET zoneinfo today filter); `runtime.publish_snapshot` adds `account` (reuses
          `equity_log.snapshot`) + cached `round_trip`; `refresh_round_trip` (45s worker job, one broker fills call) +
          `publish_monitor` (10s → `steering/monitor.json`, turns/decisions/log, secrets masked). **Console (TS src):**
          `steer_read{view}` dispatch (parser turns/decisions verbs, FileDrop.readMonitor, handleSteerRead routes
          turns/decisions/log→monitor.json — fixes verb-ignored-always-snapshot). **Console UI (submodule):** `sidebar-width.ts`
          shared reactive signal + XDG `ui.json` persist + clampWidth; `sidebar.tsx` re-export + left-edge drag handle
          (`selectable={false}`, width=dims.width−e.x); `autostock.tsx` account + round-trip blocks (PnL color, empty state,
          hide-when-absent); index.tsx unchanged (reactive via re-export). **Tests:** +10 Python (incl UTC/ET boundary +
          Hypothesis), +5 bun. **Full Python suite 292 green; bun 29 green. 0 new runtime deps.**
          **PENDING (user — opencode TUI not buildable here, submodule deps uninstalled):** R1 live drag-resize/capture +
          persistence, R3 `steer_read` view, R4 `get_fills` paper; tsgo typecheck of the 3 submodule TS files; push/merge;
          F5 merge (share the single width signal). **Gate: 2-option Code Generation completion — awaiting approval.**
    - [x] Code Generation — **APPROVED** 2026-05-30 ("계속 진행해줘"); **live R1 (drag-resize) user-confirmed**, R3/R4 deferred.
    - [x] Build and Test — **COMPLETE** 2026-05-30 (awaiting approval). Instruction docs in
          `construction/build-and-test/console-sidebar-upgrade/` (build / unit-test / integration-and-live / summary).
          Results: **Python full 292 green**, Python F6 10, **bun core 29 green** (run explicit files — bare `bun test`
          recurses the un-built submodule). Performance suite N/A (read-only UI; one 45s broker fills job + 10s file write;
          snapshot 5s / read 1.5s unchanged). Security: SECURITY-03 log-tail masked, SECURITY-11 privilege unchanged,
          SECURITY-15 fail-closed; PBT on `summarize_today_round_trips`. **Pending before merge:** submodule `tsgo`
          (deps uninstalled here), live R3/R4, push + F5 width-signal coordination. **Gate: ready for Operations? (placeholder)**
    - [x] Build and Test — **APPROVED / F6 TRACK COMPLETE** 2026-05-30 ("F6 완료 처리하고 커밋도 진행, 머지는 나중에").
          Operations = placeholder (no further work). Docs committed to **main** `60482b0`; code on branch
          `feat/console-sidebar-upgrade` (`e696630` + submodule `82e009b`), **not merged** (user: merge later).
          **Open follow-ups (post-track, user-scheduled):** submodule `tsgo` typecheck, live R3 (`steer_read` view) + R4
          (`get_fills` paper), push, and F5 merge coordination (both edit `autostock.tsx`/`index.tsx`; share the single
          width signal, F6 omits F5-owned default-on/rebrand).
    - [x] **F6 MERGED to `main`** 2026-05-30 ("F6 머지 해보자 ... 계속해줘"). Merge `6be1457`, submodule pin `00b4967`.
          **Was a reconciliation, NOT a mechanical merge:** F3 had already shipped `get_fills→FillEvent` + rewritten
          `publish_snapshot` (a stale-branch merge would have duplicated `get_fills`), and F5 had edited the SAME
          `autostock.tsx`/`index.tsx`. **Resolution:** re-applied F6's deltas fresh onto current main in worktree
          `.claude/worktrees/f6-merge` (branch `feat/f6-merge`): dropped F6's own `get_fills` and **converged on F3's**
          (refresh_round_trip converts the FillEvent stream → match_round_trips dicts); account/round_trip added to main's
          F3 `publish_snapshot`; round-trip(45s)+monitor(10s) jobs added beside F3's wake jobs; `operator-console/src` steer_read
          copied verbatim (F5 untouched it); submodule UI hand-merged onto F5's fork (its rebrand + disconnect banner preserved;
          `index.tsx` needed NO edit — F5's splash-only change left `contentWidth`/`sidebarWidth` import intact). **Full Python
          366 green, bun 29 green, working tree clean.** Submodule commit `00b4967` fetched into the main checkout's submodule
          store (HEAD-ref fetch from the worktree clone) so the pin is reachable locally. **Still NOT pushed** (user: later);
          live R3/R4 + submodule `tsgo` still pending. Stale branches `feat/console-sidebar-upgrade` + worktrees can be pruned.
    - [x] **Post-merge live fixes (2026-05-31):** (1) account/round-trip blocks were absent because the daemon was a
          pre-merge process — user reinstalled/restarted via the launcher → **account block live-confirmed** (eq/cash/pnl,
          PnL colored; "today · no closed trades"). (2) Home/splash sidebar drag didn't work — `routes/home.tsx` is a separate
          render path; first fix (transparent handle over `border:["left"]`) failed (absolute `left:0` insets inside the border
          → handle at col 1, user grabs col 0). Fixed by mirroring the session pattern exactly (opaque 1-col `theme.border` bar,
          borderless parent). Submodule `7d26d49`, main re-pin `68c95b6`. **Home drag now live-confirmed by user.**
    - [x] **F6 TRACK CLOSED (2026-05-31)** — user closed the feature ("이 feat 닫으면 되나?" → yes). All FRs delivered & merged;
          live-verified: R1 drag-resize (session + home), account block (FR-2), readability/PnL color (FR-5). **Still NOT pushed**
          (local only): pushing requires the submodule fork commits (→ `autostock-cli` remote) BEFORE the parent re-pin push.
          **Deferred (non-blocking, user-scheduled):** R3 (`steer_read{view}` turns/decisions/log), R4 (`get_fills` paper —
          round-trip populates intraday), submodule `tsgo` full typecheck, `git push`, prune stale `feat/*` branches.
    - **`/critic` adversarial review (isolated subagent) 2026-05-30 — 7 findings (2 HIGH, 4 MED, 1 LOW), ALL cross-verified
          valid vs code; reflected into requirements/FD/NFR/plan docs:** #1 [HIGH] FR-3 today round-trip is empty all day —
          `trades.jsonl` only written at `_eod` (`agent.py:133,178`), not `_intraday` → **policy fork resolved by user = B**
          (worker aggregates fills/activities at low cadence 30–60s; "0 broker call" assertion dropped; align with F3's designed
          `get_fills` activities port — no dup). #2 [HIGH] drag handle needs **`selectable={false}`** — OpenTUI default
          `selectable=true` (core 18185) → text-selection hijacks onMouseDrag; capture is set on first *drag* not down → handle
          must own capture (live spike R1; fork's logo.tsx uses selectable=false). #3 [MED] `steer_read{view}` is a 4-file change
          not "add a param" — `parser.ts:22` lacks turns/decisions read verbs, `FileDrop` has no monitor.json reader,
          `handleSteerRead` ignores verb & always returns snapshot (even `log`). #4 [MED] ET-date filter needs **UTC→ET zoneinfo**
          (`filled_at` is UTC, `trades_log.py:64`). #5 [MED] account block must **reuse `src/agent/equity_log.py::snapshot(ps)`**
          (already builds equity/cash/open_pnl/position_count) — no re-derive. #6 [LOW] poll cadence: console read 1.5s
          (`autostock.tsx:142`) ≠ daemon publish 5s (`agent.py:181`). #7 [LOW] F5 collision is logic-level (shared `index.tsx:236-243`
          memo + autostock.tsx) → width signal as a context **independent of sidebarVisible**, all consumers share one signal
          (merge contract). Verified-sound: MouseEvent.x is absolute terminal col; add_seconds_job exists; match_round_trips returns
          closed_at/realized_pnl; console reads snapshot only (NFR-1 intact). New verify items: R1 drag capture, R4 get_fills paper.
          Net F6 scope grew slightly (get_fills port shared w/ F3 + low-cadence round-trip job); 0 new runtime deps still holds.
  - **Deferred-to-FD (resolved):** width-persistence = console XDG ui.json; sourcing = publish_snapshot ext (both); FR-4 =
        steer_read{view} MCP + daemon steering/ read files; drag-handle = thin left-edge │.

## New Feature Track: Console Trading-Native Copy & Tips (F7) — ✅ DONE & MERGED TO MAIN 2026-05-31
> **MERGED 2026-05-31** (user: "개발한걸 main으로 머지하자"): fork `main` FF-merged to `576b63c` + pushed to autostock-cli;
> parent gitlink re-pinned (parent commit `631ec6e`). `autostock` now runs the trading-native console from main. Branch
> `feat/console-trading-copy` deleted (merged). Only the gitlink re-pin was committed to parent — `aidlc-state.md` + F7 doc files left
> uncommitted in the working tree because a **concurrent F8 track** (console-sidebar-status-rich) is editing the shared aidlc-docs.
> Pre-existing F6 `selectable` tsgo errors (home.tsx/sidebar.tsx) flagged to user, untouched.
> **Code Generation Part 2 + Build&Test DONE 2026-05-31** on submodule branch `feat/console-trading-copy` (off fork `main`
> `7d26d49` = F5+F6 base), commit **`576b63c`**. Worked directly in the submodule (change is submodule-only; practical equivalent
> of "worktree off F5 base"). **Changes:** `home.tsx` — locale-aware `placeholder.normal` (KO shell-locale helper → 한글 steering
> 예시, else English; shell examples unchanged); `tips-view.tsx` — TIPS rebuilt to trading-first pool (9 steering tips + 7 useful
> generic: sidebar/palette/interrupt/`/new`/`/sessions`/`/themes`/`/compact`; dropped ~90 coding/dev/config/github tips from home
> rotation), `NO_MODELS_TIP` rebranded. Copy-only; tips English-single (share rotation w/ retained English tips). **Verification:**
> tsgo **no NEW errors** (2 pre-existing F6 `selectable` drag-resize errors confirmed on clean base — unrelated); no test depends on
> changed copy; `{highlight}` balanced 17/17; TUI app-lifecycle **9/9 green**; locale detection verified (ko→true, en→false, LC_ALL
> precedence). **Remaining (user-gated, outward):** push fork branch to autostock-cli + parent re-pin + merge to main; live visual
> check. **Decisions evolved in-session:** locale→placeholder-only (tips would interleave ko/en jarringly w/ ~100 retained EN tips);
> tips→trading-first curated pool (random 1-of-pool render → keep trading dominant); safety tips→capability-framed, not mechanism.
> ── (Part-1 history below) ──
> **Stage Progress (F7):** Requirements **APPROVED** ("승인 & 계속") → User Stories **SKIP** → Workflow Planning **COMPLETE**
> (`inception/plans/f7-execution-plan.md`: all construction stages SKIP except Code Generation + Build&Test; single small unit,
> worktree off F5 base; no F5/F6 file overlap) → Functional/NFR/Infra **SKIP** → **Code Generation Part 1 plan written, awaiting approval**
> (`construction/plans/f7-copy-code-generation-plan.md`: Step1 home.tsx NL placeholders, Step2 NO_MODELS_TIP rebrand, Step3 remove 14
> clearly-coding tips, Step4 add ~12 steering tips (NL-intent+confirm, real §5 grammar), Step5 tsgo+no-regression). On approval, Part 2
> first action = create worktree `feat/console-trading-copy`; push/re-pin/merge gated on user (outward).
> **Resumed via `/ai-dlc-resume F7` 2026-05-30.** Carved out of F5. No code written yet.
> Stage = INCEPTION → Requirements Analysis **COMPLETE (minimal), awaiting approval**.
> Requirements doc: `aidlc-docs/inception/requirements/console-trading-native-copy.md`.
> **Locked decisions (concretizing answers 2026-05-30):** Q1 = **최소·외과적** tips 교체(코딩 전용 팁만 → 트레이딩-스티어링 팁;
> 일반 TUI 팁 + 실경로 config 팁 유지); Q2 = **자연어 위주** placeholder("sell half my AAPL"/"pause new entries"/
> "what are my open positions?"); Q3 = **안전/거버넌스 팁 포함**(/pending·/approve·/reject, /kill·/flatten, break-glass=Alpaca UI, lockdown).
> **Interaction model corrected (user catch 2026-05-30):** the `/buy·/pause·/approve·/status` grammar is the `autostock_steer`(mutating,
> opencode confirm `"ask"`) / `autostock_steer_read`(read, `"allow"`) **MCP tool `command` argument** — NOT TUI slash commands (verified:
> no `registerCommand` for steering verbs in the fork). Operator talks NL → agent calls the MCP tool → opencode CORE auto-gates → daemon
> RiskManager final gate; break-glass=Alpaca UI. Console-exposed grammar (hyphenated) from `operator-console/src/mcp-server.ts`. Requirements
> doc revised: §1.1 model, FR-3 reframed to NL-intent+confirm (not "type /approve"), §5 rewritten, AC-7 added. Target files verified in fork
> @ submodule 0fa8fc1. **Next on approve:** User Stories SKIP → Workflow Planning (single small unit, worktree off F5 base).
- **Goal**: Make the operator console's *copy* trading-native (not just the logo/title brand). The opencode fork's
  home prompt placeholders and rotating tips are all **coding-oriented** and off-brand for a trading-steering console.
- **Scope (in)**:
  - Home prompt placeholders (`packages/opencode/src/cli/cmd/tui/routes/home.tsx` `placeholder.normal/shell`,
    currently "Fix a TODO in the codebase" / "Fix broken tests" / "What is the tech stack…") → trading/steering examples
    (e.g. "sell half my AAPL", "/pause", "show positions", "flatten AAPL").
  - Rotating tips (`feature-plugins/home/tips-view.tsx`, ~line 200+) — replace coding tips ("opencode run -f file.ts",
    "opencode agent create", "Fix a TODO…") with steering usage tips (NL→MCP `autostock_steer`, `/pause`/`/approve`,
    sidebar panels, break-glass=Alpaca UI, lockdown). Content rewrite, NOT a string swap.
  - (optional) `debug` command `opencode version:` line (debug-only, low priority).
- **Scope (out / leave — functional, not display brand)**: real config paths `~/.config/opencode`/`opencode.json`/
  `.opencode/`, theme id "opencode", provider ids, MCP clientInfo, `opencode` binary spawns (pr.ts), pkg-manager names.
  Some tips legitimately reference the real `~/.config/opencode` path — keep those path references.
- **Built on**: F5's rebranded fork (branch `feat/console-native-launcher` / its merge). Coordinate with F6 (also edits the
  console) — F7 is copy-only (tips/placeholders), no overlap with F6's sidebar/index.tsx resize logic.
- **Extensions**: project default (Security Baseline; PBT N/A for copy). **Next action on resume**: Requirements Analysis
  (likely minimal — propose placeholder/tip copy, get user approval, apply; single small unit, worktree off the F5 base).

## New Feature Track: Console Sidebar — status.py-rich Data & Color (F8)
- **Started**: 2026-05-31. **Stage**: INCEPTION → Workflow Planning (awaiting approval).
- **Goal (user)**: 사이드바 정보가 부족 + 색 가독성 필요 → `scripts/status.py`의 풍부한 4블록을 operator-console 사이드바(`autostock.tsx`)로 이식하고 status.py식 손익 green/red+▲▼ 색 적용.
- **Built on**: F6 사이드바(merged main). 콘솔은 `snapshot.json`만 읽는 읽기전용(NFR-1) 불변; 데몬 `publish_snapshot` 발행만 확장.
- **Grounding (read 2026-05-31)**: `runtime.publish_snapshot` positions=`{qty,avg_entry_price}`(현재가/손익 없음), open_orders=`{symbol,order_id,stop_price,limit_price}`(side/역할/가격/Δ 없음), `_account_block`={equity,cash,open_pnl,position_count}(invested 없음), `fills`=일시적 새-체결(웨이크용, 최근체결목록 아님). 사이드바 폴링 1.5s, 발행 5s, round_trip 45s, monitor 10s. 서브모듈 `operator-console/cli` @ `7d26d49`(checked out).
- **Decisions (concretizing 2026-05-31)**: D1 4블록 전부 / D2 1줄압축(무손실)+드래그 word-wrap+최소폭 floor / D3 손익 green·red+▲▼ / D4 보유 current_price 재사용 + 미보유 주문심볼만 보충 fetch.
- **Cadence LOCKED (기본값 유지)**: 폴링 1.5s, 발행 5s(보유가격·주문필드 추가비용 0); 미보유 주문심볼 가격 슬로우잡 ~10–15s+캐시; recent_fills ~45s. ms 불가/불요.
- **Extensions (F8)**: 프로젝트 기본 — Security Baseline Enabled(SECURITY-03/15 적용, 대부분 N/A), PBT Partial(평가손익%/Δ%/역할/recent_fills 정렬).
- **Requirements doc**: `aidlc-docs/inception/requirements/console-sidebar-status-rich.md`.
- **Execution plan**: `aidlc-docs/inception/plans/f8-execution-plan.md`.
- **Stage Progress (F8)**:
  - [x] Workspace Detection — reused (brownfield).
  - [x] Reverse Engineering — reused (artifacts exist).
  - [x] Requirements Analysis — **APPROVED** 2026-05-31 ("일단은 유지. 승인 계속가자"). Cadence locked.
  - [~] Workflow Planning — **COMPLETE** 2026-05-31 (awaiting approval). Single unit `console-sidebar-status-rich`;
        User Stories SKIP, Application Design SKIP(→FD), Units Generation SKIP, Infra Design SKIP; Functional Design (light) /
        NFR Requirements (minimal, 0 deps) / NFR Design / Code Gen / Build&Test EXECUTE. worktree off main + 서브모듈.
  - [x] Workflow Planning — **APPROVED** 2026-05-31 ("계속 진행").
  - **CONSTRUCTION — Unit `console-sidebar-status-rich`:**
    - [x] Functional Design — **COMPLETE (light)** 2026-05-31 (awaiting approval; ran autonomously per [[feedback-autonomy-construction]]).
          Artifacts: `construction/console-sidebar-status-rich/functional-design/{domain-entities,business-logic-model,business-rules,frontend-components}.md`.
          Grounded vs status.py + runtime.publish_snapshot. **Entities:** E1 PositionRow(+current_price/market_value/unrealized_pnl)
          · E2 OrderRow(+side/order_type/current_price → role/Δ 파생) · E3 RecentFill(신규 recent_fills, get_fills top-8, 일시적 fills와 별개)
          · E4 AccountSummary(+invested) · E5 PriceBook(데몬 내부, 미보유 주문심볼 캐시, status.py _latest_prices). 역할/색/Δ/pnl%는 콘솔 순수파생.
    - [x] NFR Requirements — **COMPLETE (minimal)** 2026-05-31. 0 new runtime deps (Python: portfolio/orders/get_fills/equity_log/
          StockHistoricalDataClient 재사용; TS: OpenTUI/wrapMode/stdlib). Artifacts: nfr-requirements/{nfr-requirements,tech-stack-decisions}.md.
    - [x] NFR Design — **COMPLETE** 2026-05-31. P1 가산 스냅샷 확장(추가콜 0) · P2 PriceBook 12s 슬로우잡+30s TTL 캐시 · P3 recent_fills
          45s 슬로우잡(round_trip과 get_fills 공유 검토) · P4 단일 워커(신규 프리미티브 0) · P5 콘솔 순수파생 · P6 width floor 24→36 · P7 SECURITY-03/15.
          Artifacts: nfr-design/{nfr-design-patterns,logical-components}.md.
    - [x] Infrastructure Design — **SKIP** (로컬 데몬/TUI).
    - [~] Code Generation **Part 1 (plan)** — created 2026-05-31, **awaiting approval to enter Part 2.** Plan:
          `construction/plans/f8-code-generation-plan.md` (Step0 worktree → 1 헬퍼/필드확인 → 2 publish_snapshot 가산확장 → 3 PriceBook 12s →
          4 recent_fills 45s → 5 TS 스키마/contract → 6 autostock.tsx 렌더+색+레이아웃 → 7 width floor 24→36 → 8 PBT/bun → 9 라이브/핀).
          0 new deps. On approval, Part 2 first action = `git worktree add … -b feat/console-sidebar-status-rich main`; no code/worktree yet.
          **NOTE:** tool env intermittently lagged this session — exact TS lines / Python field names re-verified at Part 2 entry. **Gate: approve Part 1 plan to start coding.**

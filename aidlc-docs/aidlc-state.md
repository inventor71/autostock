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
  - [ ] Build and Test — final (bun tests + tsgo typecheck + verify-lockdown + python no-regression).
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

# Track F2 — Human-Steering Console for Agent Mode (archived pre-partition history)

> Migrated 2026-06-04 from the root `aidlc-state.md` archived section into this track's
> `state.md` (concurrent-tracks partition rule: root file = Track Registry only). This is
> historical record for a completed/abandoned track — the registry row in
> `aidlc-docs/aidlc-state.md` is authoritative for final status. Design/plan artifacts live
> alongside under `aidlc-docs/tracks/F2/`.

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

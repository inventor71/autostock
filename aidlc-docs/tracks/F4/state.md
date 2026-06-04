# Track F4 — Claude-Code-native Steering Console (archived pre-partition history)

> Migrated 2026-06-04 from the root `aidlc-state.md` archived section into this track's
> `state.md` (concurrent-tracks partition rule: root file = Track Registry only). This is
> historical record for a completed/abandoned track — the registry row in
> `aidlc-docs/aidlc-state.md` is authoritative for final status. Design/plan artifacts live
> alongside under `aidlc-docs/tracks/F4/`.

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

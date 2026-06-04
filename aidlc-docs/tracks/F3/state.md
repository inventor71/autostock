# Track F3 — Intraday Loop Redesign (archived pre-partition history)

> Migrated 2026-06-04 from the root `aidlc-state.md` archived section into this track's
> `state.md` (concurrent-tracks partition rule: root file = Track Registry only). This is
> historical record for a completed/abandoned track — the registry row in
> `aidlc-docs/aidlc-state.md` is authoritative for final status. Design/plan artifacts live
> alongside under `aidlc-docs/tracks/F3/`.

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

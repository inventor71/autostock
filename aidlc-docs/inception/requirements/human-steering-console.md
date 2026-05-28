# F2 — Human-Steering Console for Agent Mode — Requirements

_Status: Requirements Analysis complete (awaiting approval). Brownfield, AI-DLC track F2._
_Decided 2026-05-28 from `human-steering-console-questions.md` (Q1–Q10 answered)._

---

## 1. Intent Analysis

| Field | Value |
|---|---|
| **Request type** | New Feature (user-facing) |
| **Scope** | Multiple components (`main.py`, new console module, `Journal`, `DecisionExecutor`, orchestrator/prompts) |
| **Complexity** | Moderate→Complex (concurrency with a live daemon, agent mental-model consistency, NL parsing, forced-trade safety) |
| **Depth** | Comprehensive-leaning Requirements Analysis |

**User request (verbatim intent):** Add a console to `main.py --mode agent` that lets a human steer the autonomous PM agent in natural language (e.g. "sell AAPL"). The system must (1) **carry out** the human's intent, (2) **durably log** the intervention, and (3) keep the running agent **consistent** — the agent must become aware that a human changed the book so its journal / per-symbol theses / resting protection do not drift out of sync. **Headline value: correct an AI mistake quickly in plain language; build a human+AI co-managed trading system where the AI recognizes human intervention.**

**Integration surface (read 2026-05-28):**
- `main.run_agent()` → `modes/agent.AgentTradingMode.start()` runs a `TradingScheduler` (research/open/intraday/EOD jobs on background threads) + a `while True: time.sleep(1)` main thread.
- `agent/orchestrator.AgentTradingLoop` runs LLM turns via `agent/session.AgentSession` (a single resumable `claude -p` session per ET trading day) and **only writes to the file-based journal**.
- `agent/executor.DecisionExecutor` is the **only order-placing path**: reads `decisions.jsonl` → `RiskManager` (bracket/OCO) → `Broker`, cursor-idempotent (`.executor_state.json`).
- `agent/journal.Journal` is the durable, file-based source of truth under `workspace/`.

---

## 2. Confirmed Decisions (from clarifying questions)

| # | Decision | Answer |
|---|---|---|
| Q1 | Console runs as an **in-process REPL thread** inside `main.py --mode agent` | B |
| Q2 | **Hybrid** interpretation: structured verbs for actions + free-form NL notes | C |
| Q3 | **Echo parsed interpretation + y/n confirm** for trades (notes apply without confirm) | B |
| Q4 | Command surface: **trades + lifecycle control + context steering** | C |
| Q5 | Agent awareness: **passive channel + immediate reconcile turn** | B |
| Q6 | Forced human trades use the **same RiskManager → Broker safety gate** | A |
| Q7 | **Structured logging now**, learning loop deferred | A |
| Q8 | Develop in a **new git worktree + branch** | A |
| Q9 | Security extension: **enforced (all SECURITY rules blocking)** | A |
| Q10 | PBT extension: **partial** (PBT-02/03/07/08/09; pure functions + serialization) | B |

---

## 3. Functional Requirements

### FR-1 — In-process steering console (Q1=B)
- `main.py --mode agent` starts a console REPL on a dedicated thread alongside the scheduler. The scheduler and main loop are unaffected when no input is pending.
- **TTY-aware:** if no controlling terminal is attached (detached/headless launch), the console disables itself and logs a one-line notice — the daemon keeps trading normally (fail-safe, not fail-loud).
- A `quit`/`Ctrl-D` on the console stops only the console, not the trading daemon; `Ctrl-C` still stops the daemon as today.

### FR-2 — Hybrid command interpretation (Q2=C)
- **Structured verbs** (deterministic, no LLM) for safety-critical actions:
  - `sell <SYM>` / `sell <pct>% <SYM>` — force sell (default 100%).
  - `buy <SYM> [<notional|qty>]` — force buy (size via the safety gate).
  - `flatten <SYM>` / `flatten all` — close position(s).
  - `stop <SYM> <price>` — set/adjust a protective stop.
  - `pause` / `resume` — agent lifecycle (FR-5).
  - `halt-entries` / `allow-entries` — block/allow new agent entries (FR-5).
  - `kill` — kill-switch = `flatten all` + `pause` (FR-5).
  - `note <text>` / `directive <text>` — free-form context for the agent (FR-6).
  - `status` / `help` — read-only introspection.
- **Free-form NL** is accepted on `note`/`directive` lines verbatim (logged + fed to the agent). NL→trade parsing is **not** in v1 (structured verbs only for trades) to keep the order path deterministic; revisit later.
- Unrecognized input is rejected with a help hint — never silently guessed into an action (fail-closed, SECURITY-15).

### FR-3 — Echo + confirm for trades (Q3=B)
- For any trade/lifecycle-mutating command, the console echoes its parsed interpretation (e.g. `Interpreted as: SELL 100% AAPL @ market — confirm? [y/N]`) and executes only on explicit `y`.
- `note`/`directive`/read-only commands apply without confirmation.
- A timed-out or `N` confirmation is a no-op (fail-closed).

### FR-4 — Forced trades through the same safety gate (Q6=A)
- A confirmed trade command is turned into a `Decision`-equivalent and executed through the **existing** `DecisionExecutor` → `RiskManager` (bracket/OCO protection, circuit breaker) → `Broker` path. No second order path is created.
- The human sets direction / symbol / size intent; RiskManager still applies protection and sizing exactly as for an agent trade, preserving book consistency.
- Human-initiated decisions are tagged with `source="human"` so they are distinguishable from `source="agent"` in the journal and logs (default existing decisions = `agent`).

### FR-5 — Lifecycle control (Q4=C)
- `pause`/`resume`: a shared run-state flag the scheduled cycles honor — when paused, scheduled research/intraday/EOD turns and execution skip (cheap no-op) until resumed. Human commands still work while paused.
- `halt-entries`/`allow-entries`: block new BUY execution while still managing/exiting existing positions.
- `kill`: flatten all positions (through the safety gate) then pause. Requires confirmation (FR-3).

### FR-6 — Agent awareness: passive channel + immediate reconcile (Q5=B)
- Every intervention is appended to a dedicated journal channel (`human_directives.jsonl` + a human-readable note surfaced into the agent's prompt context) so the next scheduled turn reconciles.
- **Immediately after** a human action, the orchestrator fires an out-of-band **reconcile turn**: the agent re-reads live broker state + the new directive(s) and updates its journal/per-symbol theses/regime/watchlist so its many files don't drift. (User rationale: the agent touches many files, so reconciliation must be done well.)
- The reconcile turn is **best-effort**: a failure (e.g. LLM timeout) is logged and never kills the daemon (mirrors the existing `_launch` try/except). It is serialized with scheduled turns (see NFR-1) to avoid session collisions.

### FR-7 — Durable structured intervention log (Q7=A)
- Each intervention is recorded as a structured, append-only record: `ts`, `source="human"`, raw input text, parsed action (verb + args), optional rationale (empty in v1), and the resulting executor outcome (fill / no_order / skipped / error).
- This is the audit + future-learning substrate. Actively *teaching* the agent from these records (e.g. EOD reflection) is **deferred** — explicitly out of v1 scope.

---

## 4. Non-Functional Requirements

### NFR-1 — Concurrency & serialization (the core engineering constraint)
Steering a *running* daemon (whether via in-process REPL or files) requires a **single serialization point** so the console, the scheduled jobs, and the reconcile turn never touch the broker / executor cursor / LLM session concurrently.
- Implement a single serialized command path — a `threading.Lock` (or one-worker command queue) guarding executor calls (`execute_pending`, `run_risk_exits`, protection changes) and agent-turn invocation.
- The CLI session is single-resumable: no two turns may run concurrently → the reconcile turn and scheduled turns share the turn lock.
- The console REPL thread must never block the scheduler; it enqueues work onto the serialized path.
- **Design note (Q1):** building the serialized command path as the core means a future **file-drop front-end** (for detached/headless operation) can reuse the same queue at near-zero cost (→ effectively option C later). Deferred; v1 ships the in-process REPL only, under the assumption the trader runs in a foreground/`tmux` terminal.

### NFR-2 — Consistency / no orphaned state
- A forced exit must leave no orphaned resting protection (cancel/replace via the existing executor reconciliation), and the executor cursor must stay correct so the agent's next turn isn't confused (covered by routing through `DecisionExecutor`).

### NFR-3 — Security (extension enforced, Q9=A)
- **SECURITY-03:** the intervention log and console output MUST NOT contain secrets/API keys — only symbols, sizes, prices, and user text. (Compliant by design; reuses loguru + file logging.)
- **SECURITY-11 (secure design):** steering logic is isolated in a dedicated console module; order placement stays in `DecisionExecutor`/`RiskManager` (separation of concerns). Defense in depth = human intent + RiskManager gate + confirmation. Misuse case addressed: a fat-finger `flatten all`/`kill` requires explicit confirmation.
- **SECURITY-13 (integrity):** human-directive records are parsed with pydantic (safe deserialization, typed allowlist — same as `Decision`); human-initiated trades are auditable (actor=`human`, action, timestamp, outcome). The log is append-only.
- **SECURITY-15 (fail-closed):** unparseable/unconfirmed/timed-out commands are no-ops; reconcile-turn and command errors are caught and logged; the daemon never dies from a console error; locks released in `finally`.
- Other SECURITY rules (encryption at rest/transit, network, web headers, authN/Z, supply chain) **N/A** — local single-operator CLI, no new network/web surface, no new runtime dependency intended.

### NFR-4 — Testing & PBT (partial, Q10=B)
- Framework: **Hypothesis** (already a dev dependency since U3) — PBT-09 satisfied.
- **PBT-02 (round-trip):** `HumanDirective` record serialize→deserialize == identity.
- **PBT-03 (invariant):** command parser invariants — e.g. parsed `sell_pct ∈ (0,1]`; a parsed trade always carries `source="human"`; an unrecognized line never yields an executable action.
- **PBT-07/08:** domain-appropriate generators for command text/records; shrinking + seeded reproducibility.
- **PBT-10 (complementary):** example-based tests pin the safety-critical scenarios (confirm gate, kill-switch, paused-state skip, reconcile-turn failure tolerance) alongside the properties.

### NFR-5 — No regression to the autonomous path
- With the console unused (or detached/disabled), `main.py --mode agent` must behave exactly as today. The full existing suite (196 tests) must stay green.

---

## 5. Out of Scope (v1) / Deferred
- NL→trade parsing (LLM-mapped trades). v1 trades are structured verbs only.
- Active learning from human interventions (EOD reflection / lesson synthesis) — Q7 deferred.
- File-drop / remote front-end for **detached** operation — enabled cheaply later by NFR-1's queue.
- Interactive "why?" rationale capture (Q3=C path) — record schema leaves room (`rationale` field) but v1 doesn't prompt for it.

## 6. Open Assumption (please confirm or redirect at approval)
- **The live trader is run attached (foreground or `tmux`/`screen`), not fully detached.** This makes the in-process REPL (Q1=B) sufficient for v1. If detached operation is a hard requirement, the primary front-end should be file-drop instead (NFR-1 makes this a small change).

## 7. Extension Compliance Summary (Requirements stage)
- **Security Baseline (enforced):** SECURITY-03 / 11 / 13 / 15 are the applicable, addressed rules (see NFR-3). All others N/A for a local CLI tool. No blocking findings at requirements stage.
- **Property-Based Testing (partial):** PBT-02/03/07/08/09 mapped to the parser + record serialization (NFR-4); example-based tests cover critical paths (PBT-10). No blocking findings at requirements stage.

## 8.1 Addendum — FR-8: Human-approval gate on agent decisions (added during Functional Design, 2026-05-29, per Q8)
A symbol the human trades on (`/buy`, `/sell`, `/flatten`) becomes **human-locked**. While locked, the
agent's **discretionary** decisions (BUY/SELL) on that symbol are not auto-executed — they are parked as
`PendingApproval` and surfaced on the console (`/pending`, `/approve|/reject <id>`). Approval executes and
**unlocks**; rejection keeps the lock and increments a counter; **two rejections → denied for the day**.
The approve/reject/denied outcome is fed back to the agent (journal/prompt) so it understands and does not
blindly retry. **Exception:** protective orders (placing OCO/stop on an unprotected position, modifying an
existing OCO, `ADJUST_STOP`, `HOLD`+stop) are never gated — the "all positions protected" invariant must
not be blocked. Resting protection fills and polled risk-exits always fire (safety, gate-independent). Locks
are ET-date-scoped (auto-clear next trading day; `/unlock <SYM>` clears manually; persisted within the day).
This extends FR-4/FR-6 and is fully designed in `aidlc-docs/construction/human-steering-console/functional-design/`.

## 8. Key Requirements Summary
A TTY-aware in-process console adds **hybrid** (structured-verb + NL-note) human steering to the running agent. Trade/lifecycle commands **echo + confirm**, then flow through the **same RiskManager → Broker gate** as agent trades (no second order path). Every intervention is **durably and structurally logged** (`source="human"`), written to a journal channel the agent reads, and immediately triggers a **best-effort reconcile turn** so the agent updates its many files and stays consistent. The whole thing hangs off a **single serialized command path** (the core NFR), which also makes a future headless file-drop front-end nearly free.

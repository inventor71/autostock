# Track F26 — Operator Console Supervisor Mode (read-only full-codebase introspection)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F26
- **Title**: Operator console "supervisor mode" — read-only access to the whole autostock codebase so the steering agent can reason about its OWN behavior; normal mode stays code-blocked (MCP + permitted files only)
- **Type**: feature
- **Status**: active
- **Branch**: feat/F26 (TBD — created at Code Gen Part 2)
- **Worktree**: .claude/worktrees/F26 (TBD)
- **Submodule branch**: feat/F26 (likely — touches `operator-console/cli` opencode fork: agent/permission config)
- **Base commit**: 572db79
- **Start Date**: 2026-06-01T09:22:49Z

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | **Yes** (Q7=A) | Requirements Analysis |
| Property-Based Testing | **No** (Q9=C) | Requirements Analysis |

- **Security Baseline (ENABLED)**: core to this track — widens the trading agent's read surface to its own source. Applicable: secret exclusion (Q4: `.env*`/`secrets`/`*.key`/`logs/`/`.git/`), exfiltration surface from re-enabling web tools (Q10 pending), developer-only entry guard (Q8=A), read-only (no write tools — already structural via lockdown).
- **Property-Based Testing (DISABLED)**: track is permission/mode config, little algorithmic logic.

## Confirmed Requirements (from supervisor-mode-questions.md answers, 2026-06-01)
- **Entry**: `autostock --supervisor` launch flag is the ONLY entry (Q1=B). No TUI toggle/@mention/runtime switch.
- **Model**: launch flag selects a permission PROFILE for the whole session; supervisor = superset of normal (Q2). Same agent, more permission at launch.
- **Supervisor permissions** = normal MCP tools (incl. human-gated `ask` steer/order — Q3=B) **＋** full `$AUTOSTOCK_ROOT` read incl. submodule, EXCLUDING `.env*`/`secrets`/`*.key`/`*.pem`/`logs/`/`.git/` (Q4=A). No write tools (structural via lockdown).
- **Normal permissions** = MCP tools + web tool(s) (Q5=A + "인터넷 검색 같은 일반 툴"); source-code file reads BLOCKED; only an allowlist of operational status files readable (Q10-b pending; default `$STEERING_DIR/**` read-only).
- **Developer-only guard** (Q8=A = ①+②): (①) NO runtime permission-switch tool exists for the model (lockdown compiles out `task`; no MCP tool flips permissions) + (②) launch flag requires shell access; daemon/autonomous paths never pass it → supervisor profile is unreachable to the model/daemon. No secret token (B/D not chosen).
- **UI**: show `MODE: SUPERVISOR` badge ONLY in supervisor mode (Q6=A).
- **Web tools (Q10=B + a)**: websearch + webfetch BOTH enabled, both profiles (re-enabled vs current lockdown which compiles them out; edit/write/bash/task/patch stay removed). Exfil risk consciously accepted → AR-1.
- **File-layout finding (Q10=b)**: operator-facing state already consolidated into `$STEERING_DIR/` by daemon publish_monitor/publish_snapshot (folds workspace/turns.jsonl, workspace/decisions.jsonl, logs/autostock.log, secret-masked). raw `workspace/`+`logs/` are separate dirs but the console agent reads the aggregated view / `steer_read` MCP → **normal allowlist `$STEERING_DIR/**` is sufficient; NO consolidation refactor needed this track** (caveat: needed only if future requires reading raw files directly in normal mode).
- Requirements doc: `aidlc-docs/inception/requirements/supervisor-mode.md` (FR-1..7, NFR-1..4, Security compliance, AR-1).
- **Critic pass (2026-06-01, all code-confirmed)**: HIGH#1 secret globs must be `**/`-prefixed + deny-last (worktree-relative read patterns; else secrets readable → AR-1 void) → DESIGN-NOTE-1 보정 ①②. HIGH#2 profile selection is NEW impl (launcher strips --supervisor + sets env; opencode needs env→permission injection; fromConfig is file-only) → FR-1 mechanism + R4 concrete. MED: expand() only ~/$HOME, disabled() tool-removal order-sensitivity → 보정 ③④. LOW: web-only restore structurally safe; badge file = sidebar/autostock.tsx. verify-lockdown path-case tests = blocking.

## Scope
Add a second operating posture ("supervisor mode") to the opencode-fork operator console so the
human can ask the steering agent to explain how its own daemon behaves (e.g. "summarize what happens
in a research turn") backed by the ACTUAL source — not guesses.

Grounding from current code (read during inception):
- Launcher `operator-console/launcher/config.ts:110` sets `AUTOSTOCK_LOCKDOWN=on`; console cwd = the
  `cli` submodule, so the agent's project dir is the cli tree. `AUTOSTOCK_ROOT` (parent repo) is
  already exported to the console env (`config.ts:107`).
- Code access to the parent autostock Python repo is blocked today by the `external_directory`
  permission (not allowlisted in `opencode.json` whose `"*": "deny"`). That is the exact wall the
  agent hit in the user's transcript.
- `registry.ts` lockdown COMPILES OUT edit/write/bash/task/fetch/patch under lockdown — only
  read/glob/grep/lsp + MCP survive. So "read-only" is already structurally guaranteed; supervisor
  mode does NOT need new write tools and MUST NOT add any (self-modification = self-destructive).
- opencode has a native agent/persona model (`packages/opencode/src/agent/agent.ts`) with per-agent
  `external_directory` / `readonlyExternalDirectory` permission — a natural carrier for the mode.

Likely design (to confirm in design stage): a distinct read-only "supervisor" opencode agent/mode
whose `external_directory` is allowed scoped to `$AUTOSTOCK_ROOT`, with an introspection system
prompt; normal/default agent keeps code blocked. Open questions on switching UX, normal-mode
tightening, trading-tool availability in supervisor mode, and secret exclusion — see questions file.

Related: [[f4-steering-runtime-wiring]] [[console-native-launcher]] [[f9-gated-alpaca-orders]]
[[f19-...]] (opencode perm keys), [[steering-console-redesign]].

## Stage Progress
- [x] Workspace Detection — brownfield; RE artifacts exist (architecture.md) → reverse-engineering skipped
- [x] Requirements Analysis — standard depth; Q1–Q10 answered, requirements.md APPROVED 2026-06-01 (DESIGN-NOTE-1 approach (1) chosen + feasibility-verified against permission engine)
- [x] User Stories — SKIP (single operator persona; config/permission-level change, no new user journeys)
- [x] Workflow Planning — plan at inception/plans/supervisor-mode-execution-plan.md (3-package seq: fork→launcher→TUI; App Design + Code Gen + Build&Test to run; User Stories/Units skipped) — awaiting approval
- [x] Application Design — `inception/application-design/supervisor-mode-design.md`. R4 SOLVED: profile injection via `OPENCODE_PERMISSION` env (flag.ts:67 → config.ts:746 mergeDeep) — launcher emits per-profile permission JSON; opencode.json reduced to static (MCP+web+`*:deny`), read/glob/grep/lsp/external_directory supplied by env so ordering is launcher-controlled. Web restore = readOnly array + tool.fetch/search. Exact JSON+ordering+coord-systems (read=worktree-relative, external_directory=absolute) specified. AR-2 (glob/grep path-name leak in supervisor) accepted. No opencode engine patch. — **APPROVED 2026-06-01 ("응")**; Construction queued (worktree feat/F26 + submodule branch + code per §7 order). May run in parallel with F28 inception.
- [ ] Units Generation — skip (single cohesive change across fork+launcher)
- [ ] Construction (per-unit Code Generation) — worktree `.claude/worktrees/F26` (feat/F26), submodule feat/F26@012ab3f, bun install+tsgo OK (2026-06-01). Submodule init needed manual fix: gitlink 012ab3f was unpushed-local → fetched from local main submodule.
  - [x] C1 fork `opencode.json`: added `webfetch`/`websearch`:"allow"
  - [x] C2 fork `registry.ts`: added `tool.fetch`+`tool.search` to lockdown `readOnly`; edit/write/task/patch stay absent
  - [x] C3 launcher `config.ts`: `buildPermissionProfile(cfg,supervisor)` + `consoleEnv()` sets `AUTOSTOCK_SUPERVISOR` + `OPENCODE_PERMISSION` (scrubs stale supervisor when normal)
  - [x] C4 launcher `cli.ts`: detect+STRIP `--supervisor`, pass to consoleEnv
  - [x] C5 fork sidebar `autostock.tsx`: `MODE: SUPERVISOR · read-only` badge (theme().warning) when `AUTOSTOCK_SUPERVISOR==="on"`
  - [x] C6 tests: launcher F26 tests (4) + registry.test web-survive + verify-lockdown 2-profile path cases
  - [x] C7 (critic-2 HIGH) supervisor secret globs: add slash-less root variants (`.env*`/`secrets/**`/`logs/**`/`.git/**`) + `*.key`/`*.pem` (dotall) — fixes worktree-ROOT secret (cli/.env=token) read leak
  - [x] C8/C9/C10 (critic-2): remove orphaned `list` from opencode.json; cli.ts handles `--supervisor=` form; verify-lockdown models REAL merged config (`{...opencode.json,...profile}`) + root-level secret cases
  - [x] C11 (websearch ENABLED — user: "엄청 많이 쓴다"): launcher `consoleEnv()` injects `OPENCODE_ENABLE_EXA="true"` → opens webSearchEnabled gate for ALL providers; Exa backend `mcp.exa.ai/mcp` works KEYLESS (mcp-websearch.ts:4-6); `EXA_API_KEY` passthrough for higher limits; respects an operator-set OPENCODE_ENABLE_PARALLEL/EXA override. +3 launcher tests (38/38).
- [x] Build & Test — automated: verify-lockdown 43/43 ✅, registry.test 16/16 ✅, launcher.test 38/38 ✅, tsgo 19/19 ✅. Runtime: docker-verify attach confirmed normal (Read . blocked, websearch, MCP, sidebar) + supervisor (full code read, .env denied, MODE: SUPERVISOR badge) — user verified 2026-06-01.

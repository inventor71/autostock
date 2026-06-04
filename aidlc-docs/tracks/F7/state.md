# Track F7 — Console Trading-Native Copy & Tips (archived pre-partition history)

> Migrated 2026-06-04 from the root `aidlc-state.md` archived section into this track's
> `state.md` (concurrent-tracks partition rule: root file = Track Registry only). This is
> historical record for a completed/abandoned track — the registry row in
> `aidlc-docs/aidlc-state.md` is authoritative for final status. Design/plan artifacts live
> alongside under `aidlc-docs/tracks/F7/`.

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

# Track F5 — Console-native Launcher & Rebrand (archived pre-partition history)

> Migrated 2026-06-04 from the root `aidlc-state.md` archived section into this track's
> `state.md` (concurrent-tracks partition rule: root file = Track Registry only). This is
> historical record for a completed/abandoned track — the registry row in
> `aidlc-docs/aidlc-state.md` is authoritative for final status. Design/plan artifacts live
> alongside under `aidlc-docs/tracks/F5/`.

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

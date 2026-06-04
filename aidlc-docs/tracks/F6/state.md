# Track F6 — Console Sidebar Upgrade (archived pre-partition history)

> Migrated 2026-06-04 from the root `aidlc-state.md` archived section into this track's
> `state.md` (concurrent-tracks partition rule: root file = Track Registry only). This is
> historical record for a completed/abandoned track — the registry row in
> `aidlc-docs/aidlc-state.md` is authoritative for final status. Design/plan artifacts live
> alongside under `aidlc-docs/tracks/F6/`.

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

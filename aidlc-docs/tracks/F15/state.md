# Track F15 — docker-verify `attach` mode (full daemon + TUI runtime, TEST account)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F15 (F14 was taken by a concurrent session — daemon-wedge self-heal)
- **Title**: docker-verify `attach` mode — full daemon+TUI on the TEST account
- **Type**: feature (verification-harness tooling; F10→F11→F12 lineage)
- **Status**: merged (→ main `98090fa`, 2026-05-31)
- **Branch**: feat/F15
- **Worktree**: .claude/worktrees/F15
- **Submodule branch**: — (parent-repo files only: `scripts/verify.sh`,
  `docker-compose.verify.yml`; the submodule is mounted+run at runtime but NOT modified)
- **Base commit**: e8d99a6
- **Start Date**: 2026-05-31T03:52:19Z

## Extension Configuration
- **Security Baseline**: Enabled — applicable: SECURITY-15 (fail-closed: `attach` keeps
  F10/F12's preflight so it never loads prod `.env`/account); SECURITY-03 (no secrets in
  logs — the steering token is never printed). Reuses the existing `.env.test` isolation
  (TEST paper account only). Others N/A.
- **Property-Based Testing**: Disabled — shell/compose glue; validated by `docker compose
  config` + a time-boxed live daemon-boot→snapshot check, not property tests.

## Scope
Add a fourth docker-verify mode, **`attach`**, beside `typecheck` / `unit` / `smoke`, that
runs the **full runtime**: the daemon (`main.py --mode agent --steering`) in the background
publishing `steering/snapshot.json`, plus the operator console TUI in the foreground for the
user to attach to (`docker compose run --rm -it attach`). **Same as prod except the account**
— real claude (`claude_code` via the host `~/.claude`, mounted **rw** so live turns can write
session state, unlike `smoke`'s `:ro`), real Alpaca **paper TEST** endpoint, daemon+TUI wired
exactly as prod (minus systemd — run as plain processes in the container).

Built so it can attach-test **any** worktree (incl. F13's sidebar change) once this lands on
`main` and that worktree picks it up. Related: [[console-sidebar-upgrade]], F13 sidebar change,
[[f4-steering-runtime-wiring]], [[console-native-launcher]], [[daemon-claude-cli-path]].

### Isolation / no-junk requirements
- Keep F12's fail-closed `preflight()` (AUTOSTOCK_ENV_FILE set + no prod `/app/.env`).
- Daemon runtime writes (`/app/steering`, `/app/workspace`, `/app/logs`) → **named volumes**,
  so no root-owned files land in the bind-mounted worktree (host can still `git worktree remove`).

## Decisions (locked)
- New compose **service** `attach` (not a reuse of `verify`) so it can carry `tty/stdin`,
  `~/.claude:rw`, and the runtime volumes without weakening `smoke`'s `:ro` guarantee.
- New `attach` mode in `scripts/verify.sh`: install console deps → launch daemon (bg) →
  wait for first `snapshot.json` → exec console TUI (fg). Trap kills the daemon on exit.

## Cross-track note (F13 testability)
The harness reads `scripts/verify.sh` from the **mounted** worktree (`ENTRYPOINT bash
scripts/verify.sh`, WORKDIR `/app` = bind mount). So to attach-test F13's sidebar change, the
F13 worktree must carry this attach-enabled `verify.sh` + compose. Plan (user-approved): land
F15 on `main`, then F13 picks it up (merge/rebase main) and runs `attach` from its own worktree.

## Stage Progress
- [x] Workspace Detection — brownfield; RE artifacts exist → RE skipped
- [x] Requirements Analysis — minimal; user spec explicit (attach = full daemon+TUI, TEST acct, else prod-identical)
- [x] User Stories — skip (operator tooling, no new persona)
- [x] Application Design — skip (extends existing harness; no new app component)
- [x] Units Generation — skip (single unit: harness glue)
- [x] Construction — verify.sh `attach` mode + compose `attach` service (done)
  - [x] `scripts/verify.sh` — `attach` mode (install console deps → daemon bg → wait snapshot → console TUI fg; trap kills daemon)
  - [x] `docker-compose.verify.yml` — `attach` service (tty + `~/.claude:rw` + steering/workspace/logs volumes)
- [x] Build & Test — `bash -n` OK; `docker compose config -q` OK; **live daemon-boot probe passed**:
      daemon booted on the TEST account, scheduler started, **snapshot.json published in 9s** with all
      keys (recent_fills/account/round_trip/…), real claude research turn started (model=opus). Preflight
      isolation held (no prod `/app/.env`). Only the interactive TUI render is left for the human to eyeball.

## Status: built & daemon-validated — NOT committed/merged
Changes (parent repo only): `scripts/verify.sh` (+attach mode), `docker-compose.verify.yml` (+attach
service). Uncommitted on `feat/F15`. Not merged — commit/merge only when the user asks.

## Findings from the live probe (important)
- **The TEST paper account is empty: `recent_fills: 0`, `positions: 0`.** So attaching now shows an
  empty `fills` section → **F13's date prefix is NOT visible via the live daemon path** (no fills to
  date-stamp). To see F13 live you need fills on the TEST account (let the daemon trade once market is
  open, place paper trades, or seed a snapshot fixture).
- **Two gates remain before F13 is visible via attach:** (a) the F13 worktree must carry this attach
  harness (land F15 on `main`, then F13 merges/rebases — the mounted `verify.sh` is what's executed);
  (b) the account needs (multi-day) fills.
- **Mountpoint dirs**: docker creates empty root-owned `steering/ workspace/ logs/ node_modules`
  mountpoints in the worktree (data lives in named volumes). Same as the existing `node_modules`
  mountpoint; gitignored, but teardown (`git worktree remove`) may need sudo to clear them.

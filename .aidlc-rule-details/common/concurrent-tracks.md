# Concurrent Multi-Track Development (solo, local)

## Why this rule exists
This is a **single-developer, local** project where **several features are developed
concurrently**, each in its own git worktree. Progress state must therefore be partitioned per
track: if two tracks shared one mutable `aidlc-state.md` / `audit.md`, their sessions would
read-then-write and clobber each other. This rule removes that hazard.

## Core principle: partition, don't lock
> **Every state/audit file has exactly one writer.** No file locks.

File locks are the wrong tool for a git-backed doc edited by a human+agent loop (stale locks
when an agent dies, no clean cross-worktree "wait"). Instead, **eliminate shared mutable
state** by giving each track its own files. The only file multiple tracks ever touch is the
lightweight **Track Registry**, edited just twice per track (create + close) — rare enough to
resolve with `git pull --rebase`.

## What a "track" is
- A **track** = one feature/refactor/deprecate effort, developed in its own worktree.
- Each track has a stable **Track ID**: `F1`, `F2`, … (next id = max existing + 1). Refactor
  and deprecate efforts are tracks too (e.g. `R1`, `D1`) and follow the same partition rules.
- A track owns exactly one branch.

## File layout
```text
aidlc-docs/
├── aidlc-state.md            # Track Registry ONLY (thin index). Rarely edited.
├── audit.md                  # GLOBAL timeline. Append-only, written ONLY at merge-time.
└── tracks/
    ├── _TEMPLATE/            # copy this to start a track
    │   ├── state.md
    │   └── audit.md
    ├── F9/
    │   ├── state.md          # F9's full stage progress / extension config / scope.
    │   ├── audit.md          # F9's append-only audit log.
    │   ├── inception/        # F9's requirements/ plans/ user-stories/ application-design/
    │   └── construction/     # F9's plans/ {unit}/{functional-design,nfr-*,code}/ build-and-test/
    │                         #   ALL of the above: SINGLE WRITER = the F9 worktree session.
    └── …
```
- **Per-track docs all live under `tracks/<id>/`**: `state.md`, `audit.md`, and every phase
  artifact (requirements, plans, functional/NFR design, build-and-test) in `inception/`+
  `construction/` subdirs mirroring the global layout. Author them in the worktree so `main`
  stays clean (no stray uncommitted docs when `/ai-dlc-merge` starts). The top-level
  `aidlc-docs/inception/` + `construction/` dirs are shared/pre-partition only.
- **Per-track `state.md`**: everything that used to go in an `aidlc-state.md` feature-track
  section — stage progress checkboxes, extension config, construction scope, design notes.
- **Per-track `audit.md`**: every user input / approval / AI action for this track, append-only,
  ISO 8601 timestamps, raw user input (never summarized) — same format as before, just scoped.
- **Root `aidlc-state.md`**: demoted to the **Track Registry** (table below) plus archived
  pre-partition history. Do NOT add new per-track detail here.
- **Root `audit.md`**: a global cross-track timeline. A track appends to it **only at merge**
  (fold a one-line summary), never mid-flight — so there is no concurrent append race.

## Track Registry (in root aidlc-state.md)
A single table is the authority for which tracks exist and where they live:

```markdown
## Track Registry
| ID | Title | Status | Branch | Worktree | Base commit | Updated |
|----|-------|--------|--------|----------|-------------|---------|
| F9 | … | active | feat/… | .claude/worktrees/… | <sha> | 2026-… |
```
- `Status` ∈ `active` / `merged` / `abandoned`, plus the transient `merge-awaiting` a track sets on
  **its own** `tracks/<id>/state.md` when Build & Test passes (the standard hand-off — see
  `construction/build-and-test.md` Step 8). `merge-awaiting` enqueues the track for `/ai-dlc-merge`;
  the registry row stays `active` until that command flips it to `merged` at actual merge time.
- A registry row is written at track **creation** and flipped at **merge/close**. These are the
  only two cross-track edits; serialize them with `git pull --rebase` before committing.

## MANDATORY worktree gate
**No application code may be generated outside a worktree.** Enforced as a hard, blocking gate.

> **One command does all of this:** `scripts/worktree-setup.sh <track> [--ts] [--py]` creates the
> worktree, runs the verification bootstrap (below), and links the main `.env`. Prefer it over the
> manual steps.

Before Code Generation **Part 2** (actual coding), the track MUST be on its own worktree branch:
```bash
git worktree add .claude/worktrees/<track> -b feat/<track>
```
If the session is on the default branch (`main`) with uncommitted code changes, **refuse to
generate code** and create/switch to the worktree first. Inception/design docs (markdown in
`aidlc-docs/tracks/<id>/`) may be authored before the worktree exists; code may not.

`/ai-dlc-status` flags a violation: uncommitted code changes in the `main` working tree.

### Verification bootstrap — make the worktree verifiable in place (don't defer typecheck)
A fresh worktree has **no `node_modules` and no `tsgo` binary** for the console
(`operator-console/cli` — both are gitignored build output), so `tsgo`/typecheck silently can't run
and verification keeps getting punted to "the user's machine". This is **cheap to fix, not a heavy
network op**: bun's global cache is warm (~2.6G) and bun's default backend is hardlinks, so
`bun install --frozen-lockfile` in the worktree is a near-offline hardlink farm (seconds, ~no disk).
The recurring real blockers were (a) `bun` not on PATH in a bare shell (it lives at `~/.bun/bin` —
same class as the daemon claude-CLI PATH bug), and (b) assuming the install needs the network. So:

- **TS console track**: run `scripts/worktree-setup.sh <track> --ts`. It ensures `~/.bun/bin` on
  PATH, runs `bun install --frozen-lockfile`, and verifies `node_modules/.bin/tsgo` exists. Then
  typecheck **in the worktree**:
  `(cd .../operator-console/cli && PATH=~/.bun/bin:$PATH bun run typecheck)`. Only defer to the
  user's machine if `bun` is genuinely unavailable or the lockfile changed and the cache is cold.
- **Python track**: `scripts/worktree-setup.sh <track> --py` symlinks the main `.env` into the
  worktree (pydantic loads it). Run live (paper-account, read-only) checks with the main venv
  python — see the `worktree-live-verification` memory.
- **Containerized verification (F10, zero prod impact)**: `scripts/worktree-setup.sh <track>
  --docker-verify` scaffolds `.env.test`, then prints the
  `docker compose -f docker-compose.verify.yml run --rm verify {typecheck,unit,smoke}` commands. The
  image bakes the python/bun/claude toolchain; CODE is bind-mounted so it verifies the live worktree.
  Isolation is structural: the container sets `AUTOSTOCK_ENV_FILE=/app/.env.test`, so it loads a
  **TEST paper account** only — the prod `.env`/account/systemd daemon are never referenced. Real LLM
  is the host `~/.claude` mounted read-only (no stub). Use this when you want a reproducible run
  decoupled from host toolchain state; the in-place `--ts`/`--py` paths above remain fine for quick
  local checks.

> **Registry row ⇒ per-track record (no exceptions, even for lean hotfixes).** If a change gets a
> row in the Track Registry, it MUST have a `aidlc-docs/tracks/<id>/state.md` — at minimum a few
> lines (title, status, branch/merge commit, what changed, verification). Do NOT ship a track as
> "registry row + global audit one-liner only"; that leaves `tracks/` inconsistent with the registry.
> A tiny fix/follow-up may skip the full AI-DLC stages, but never the per-track `state.md` stub.

## Track lifecycle
1. **Create.** Pick next `Fn`. `mkdir aidlc-docs/tracks/<id>`, copy `_TEMPLATE/{state.md,audit.md}`.
   Add a registry row (`active`). Create the worktree **before** any code generation. (Even a lean
   hotfix track creates `tracks/<id>/state.md` here — see the note above.)
2. **Work.** All progress, audit, and phase docs go under `tracks/<id>/` only (state/audit +
   `inception/`+`construction/` artifacts). Never touch another track's files or the root files
   (except a registry row update if the title/base changes).
3. **Merge / close.** Prefer **`/ai-dlc-merge`** — a single-runner orchestrator that merges all
   `merge-awaiting` tracks sequentially (rebase each onto the just-updated main → verify → merge →
   close), so concurrent tracks can't tangle the shared registry/audit or land on a stale base.
   It flips the registry row to `merged`, appends a **one-line** summary to the global root
   `audit.md`, and removes the worktree (`git worktree remove …`) + branch. (Manual single-track
   merge remains possible, but run the orchestrator from one place to keep merges serialized.)

## What is still global / shared
- The **Track Registry** (root `aidlc-state.md`).
- The **global timeline** (root `audit.md`) — merge-time appends only.
- The rule files under the rule-details dir and `CLAUDE.md` — changing process itself is a track too.

## Quick checklist for any agent starting work
- [ ] Am I in a worktree for my track? If coding and on `main` → stop, create worktree.
- [ ] Does my track have `aidlc-docs/tracks/<id>/{state.md,audit.md}`? If not → create from template + register.
- [ ] Am I about to edit root `aidlc-state.md`/`audit.md` mid-flight? → Don't. Use my track files.
- [ ] Am I writing a phase doc to top-level `inception/`/`construction/`? → Don't. Put it under `tracks/<id>/`.

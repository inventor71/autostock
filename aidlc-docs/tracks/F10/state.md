# Track F10 — Containerized verification harness (zero production impact)

> Per-track state. Single writer = this track's session. Root `aidlc-state.md` = registry only.
> See `.aidlc-rule-details/common/concurrent-tracks.md`. Full design: `~/.claude/plans/main-sprightly-wadler.md`.
> NOTE: started as "F9" but a concurrent session had already claimed F9 (console-alpaca-orders);
> the registry made the collision visible, so this track took F10. Worktree/branch unaffected.

## Track Info
- **Track ID**: F10
- **Title**: Containerized verification harness (Track A; prod→Docker = Track B, deferred)
- **Type**: feature/infra
- **Status**: active
- **Branch**: feat/docker-verify
- **Worktree**: .claude/worktrees/docker-verify
- **Submodule branch**: — (F10 does NOT edit submodule source; verify only typechecks it)
- **Base commit**: a0b882d
- **Start Date**: 2026-05-31

## Goal
Automated, reproducible verification that **never touches production**. Docker sandbox bakes the
python/bun/claude toolchain, runs against a **test paper account** via `.env.test`, uses the
**real `claude`** (host `~/.claude` mounted ro — no stub). Prod systemd daemon + account + state
untouched.

## Decisions (locked 2026-05-31)
- Scope: Track A (verification container) now; prod→Docker later (Track B).
- Isolation: dedicated `.env.test` → existing test paper account; prod `.env` NEVER mounted.
  `config.py` gets `AUTOSTOCK_ENV_FILE` override (key safety mechanism).
- **LLM = real claude in Track A too** (no stub — a stub hides command-surface/integration gaps,
  e.g. limit-buy not expressible in console commands — the very thing the concurrent F9 track fixes).
  `~/.claude:ro` mounted.
- **Unit tests stay deterministic** (internal in-test doubles; do NOT call real LLM). The real-LLM
  integration/command-surface smoke is a separate opt-in layer against `.env.test`.
- Docker not installed in WSL2 → Step 0 = install/bootstrap (needs sudo; user runs).

## Stage Progress
- [x] Requirements + Workflow Planning — captured via plan file + Q&A (design approved).
- [ ] User Stories — SKIP (internal infra/tooling).
- [ ] Application/Units/Infra Design — folded into the plan.
- [~] Construction (single unit `verification-harness`):
  - [x] Step 0 — Docker installed & verified by user (`docker compose v5.1.4`, `hello-world` OK).
        Earlier "docker NOT on PATH" was only my sandboxed Bash shell, not the host.
  - [x] Step 1 — `.env.test.example` + `config.py` `AUTOSTOCK_ENV_FILE` override (verified: default
        unchanged `paper=True`, override honored) + `.gitignore` `.env.test`. **Committed `5befb68`**.
        (`.env.test` itself = user fills with the TEST paper account.)
  - [x] Step 2 — real-claude wiring: `Dockerfile.verify` installs the claude CLI; `~/.claude:ro`
        mount in `docker-compose.verify.yml`. **Verified in-container**: `claude --version` →
        `2.1.158 (Claude Code)` through the ro mount (no `:rw` needed for `--version`).
  - [x] Step 3 — `Dockerfile.verify` (+ `build-essential` for node-gyp/tree-sitter native addons),
        `docker-compose.verify.yml`, `scripts/verify.sh` (modes all|typecheck|unit|smoke).
        **Committed `676adff`.** Image builds OK (CPU torch + pyproject deps).
  - [x] Step 4 — `worktree-setup.sh --docker-verify` (host-inits submodule + scaffolds .env.test +
        prints compose cmds) + `concurrent-tracks.md` container-verify note. **Committed `27ee8b2`.**
- [~] Build & Test — verified in-container against the worktree:
  - [x] `typecheck` — operator-console (bun/tsgo) **19/19 packages OK**.
  - [x] `unit` — pytest **376 passed**, deterministic/offline (in-test doubles; no real LLM/Alpaca).
  - [x] `smoke` — **PASSED** with real TEST keys. `claude --version` 2.1.158 via `~/.claude:ro`;
        read-only Alpaca on `.env.test` → account `PA3F5JU0T43K` (id `128f658d-…`, ACTIVE,
        equity 1,000,000 paper default). Read-only, NO orders. *(Full agent/command-surface
        smoke — AAPL-limit-order class — still TODO next iteration.)*

## RESUME HERE (2026-05-31, after docker-group relaunch — harness BUILT & GREEN)
**Status:** Steps 0–4 done & committed (`5befb68`, `676adff`, `27ee8b2` on `feat/docker-verify`).
typecheck (19/19) + unit (376) pass in-container; smoke's real-LLM path proven. **ONE gate left:**
fill `.env.test` with **real TEST paper-account keys**, then run `... run --rm verify smoke` to
confirm the account id printed is the TEST account (≠ prod). After that → merge.

**To finish (next):**
1. User fills `${WT}/.env.test` (`ALPACA_API_KEY`/`ALPACA_SECRET_KEY` = the TEST paper account).
2. `cd <worktree> && docker compose -f docker-compose.verify.yml run --rm verify smoke`
   → expect: `claude --version`, then account id/number/status/equity; eyeball it is TEST not prod.
3. Merge `feat/docker-verify` → main (registry row F10 → merged, global audit one-liner, update the
   `worktree-live-verification` memory to point at the container path). *Full agent/command-surface
   smoke — the AAPL-limit-order class — remains a TODO next iteration.*

---
### (archived) original relaunch note
**Why relaunch:** my Bash sandbox could NOT reach the docker socket (`permission denied`, shell not
in `docker` group). The new shell IS in the docker group → `docker build`/`run` work directly now.

**State on disk (worktree `.claude/worktrees/docker-verify`, branch `feat/docker-verify`):**
- Committed (`5befb68`): `config/config.py` (AUTOSTOCK_ENV_FILE), `.env.test.example`, `.gitignore`,
  `scripts/setup-docker-wsl2.md`.
- Uncommitted on disk: `Dockerfile.verify` (toolchain image: python3.12 + node→claude CLI + bun +
  CPU-torch + `.[dev]` deps from pyproject; CODE bind-mounted at runtime, not COPYed).

**Next actions (in order):**
1. **Write `docker-compose.verify.yml`** (service `verify`): build `Dockerfile.verify`;
   `working_dir: /app`; bind-mount the worktree `.:/app`; `env_file: [.env.test]`;
   `environment: AUTOSTOCK_ENV_FILE=/app/.env.test, PYTHONPATH=/app`; mount `${HOME}/.claude:/root/.claude:ro`;
   named volume `verify-node-modules:/app/operator-console/cli/node_modules`.
2. **Write `scripts/verify.sh`** — modes `all|typecheck|unit|smoke` (arg → CMD):
   - typecheck: `(cd operator-console/cli && bun install --frozen-lockfile && bun run typecheck)`
   - unit: `PYTHONPATH=/app pytest -q` (deterministic/offline; quarantine any net test by marker).
   - smoke (real LLM, test account): `claude --version` + tiny real prompt to confirm auth via mount;
     read-only Alpaca on `.env.test` (`get_account`/`get_all_positions`) and **print account id to
     confirm it is the TEST account (≠ prod)**. NO orders in first cut. *Full agent/command-surface
     smoke (the AAPL-limit-order class) = TODO next iteration.*
3. **Host prep before running** (do NOT do these inside the container — see gotcha):
   - `cp .env.test.example .env.test` and fill the **test** paper account keys (typecheck/unit run
     fine with dummy values; smoke needs real test keys).
   - Init the submodule IN THE WORKTREE: `git -C <main> -C .claude/worktrees/docker-verify submodule
     update --init operator-console/cli` (the worktree's submodule is NOT initialized; `git worktree
     add` doesn't init submodules).
4. **Build + run** from the worktree dir:
   - `docker compose -f docker-compose.verify.yml build`
   - `docker compose -f docker-compose.verify.yml run --rm verify typecheck`
   - `... run --rm verify unit`
   - `... run --rm verify smoke`
5. Iterate on build/runtime errors, then **Step 4** (wire into `worktree-setup.sh --docker-verify` +
   `concurrent-tracks.md` "verification = container" + update `worktree-live-verification` memory),
   then commit the Docker artifacts on `feat/docker-verify`.

**Gotchas discovered (carry forward):**
- **Git-worktree + container:** the worktree's `.git` is a *pointer* to `<main>/.git/worktrees/...`
  which is OUTSIDE the mounted `/app` → `git` commands inside the container FAIL. So init the
  submodule on the HOST; `verify.sh` must NOT run `git submodule update` — just `bun install` on
  the already-present files (check presence, error clearly if missing).
- **`~/.claude` read-only mount** may break if the claude CLI needs to write session/cache state.
  If a real `claude -p` errors on write, try `:rw` (mutates host login state — caution) or set
  `CLAUDE_CONFIG_DIR` to a writable copy. Discover at runtime.
- **Image size/time:** torch+transformers are heavy → Dockerfile uses **CPU torch** + reads deps
  from `pyproject.toml` (no duplicate list); first build is slow, later builds cache the dep layer.
- **Compose run dir:** run `docker compose` from the worktree dir so `.:/app` mounts the worktree
  code (not main).
- Root `aidlc-state.md` is a HOT file (multiple sessions editing live this session) — F10 registry
  row + this state file are in the working tree; commit only isolated branch work, avoid racing the
  root file (per `concurrent-tracks.md`). F9 (console-alpaca-orders) is a separate concurrent track.

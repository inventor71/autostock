# Track F11 — Verify-harness ergonomics (clean worktree + reuse main .env.test)

> Per-track state. Single writer = this track's session. Root `aidlc-state.md` = registry only.
> See `.aidlc-rule-details/common/concurrent-tracks.md`. Lean follow-up to F10 (no design phase).
> NOTE: this record was backfilled — F11 was originally run as a lean hotfix with only a registry
> row + global audit one-liner; the per-track file is added here for consistency with F8/F10.

## Track Info
- **Track ID**: F11
- **Title**: Verify-harness ergonomics (clean worktree + reuse main .env.test)
- **Type**: fix/infra (follow-up to [[F10]] containerized verification harness)
- **Status**: merged
- **Branch**: feat/verify-ergonomics (deleted post-merge)
- **Worktree**: .claude/worktrees/verify-ergonomics (removed post-merge)
- **Submodule branch**: — (no submodule source change)
- **Base commit**: 9390552
- **Merge commit**: 24dc367
- **Date**: 2026-05-31

## Goal
Fix two ergonomics gaps in the F10 verify harness discovered while closing F10 out.

## Problems addressed
1. **Root-owned leftovers blocked worktree cleanup.** The verify container runs as root and wrote
   `__pycache__` / `.pytest_cache` / `.hypothesis` INTO the bind-mounted worktree as `root:root`, so
   the host couldn't `git worktree remove` without sudo. Would recur on every run.
2. **TEST creds re-entered per worktree.** `--docker-verify` scaffolded an empty `.env.test` from the
   example each time, forcing the user to refill keys.

## Changes (merged 24dc367)
- `docker-compose.verify.yml`: `PYTHONDONTWRITEBYTECODE=1` + `HYPOTHESIS_STORAGE_DIRECTORY=/tmp/hypothesis`.
- `scripts/verify.sh`: pytest `-p no:cacheprovider` (no `.pytest_cache`).
- `scripts/worktree-setup.sh` (`--docker-verify`): COPY `${MAIN_ROOT}/.env.test` into the new worktree
  when present (copy, not symlink — a symlink dangles inside the container mount), else fall back to
  the example. Keep the canonical TEST keys once at the main root; future tracks pick them up.

## Verification
- unit 376 passed in-container; **0 stray cache dirs** in the worktree afterward; the test worktree
  then removed cleanly with **no sudo**.

## Follow-up
- F11's cleanup covered only the **python** writers. The **JS toolchain** (bun/turbo/tsgo) still left
  root-owned `.turbo` / nested `node_modules` / `*.tsbuildinfo` — completed in [[F12]].

## Memory
- [[worktree-live-verification]] updated with the container path + ergonomics.

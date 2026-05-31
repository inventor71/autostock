# Track F12 — Verify-harness hardening (critic review)

> Per-track state. Single writer = this track's session. Root `aidlc-state.md` = registry only.
> See `.aidlc-rule-details/common/concurrent-tracks.md`. Lean follow-up to F10/F11 (no design phase).
> NOTE: backfilled for consistency with F8/F10 (originally a registry row + global audit one-liner).

## Track Info
- **Track ID**: F12
- **Title**: Verify-harness hardening (critic: account pin + fail-closed preflight)
- **Type**: fix/security-hardening (follow-up to [[F10]] / [[F11]])
- **Status**: merged
- **Branch**: feat/verify-hardening (deleted post-merge)
- **Worktree**: .claude/worktrees/verify-hardening (removed via `rm -rf` + `git worktree prune`)
- **Submodule branch**: — (no submodule source change; submodule inited in worktree for typecheck)
- **Base commit**: 4d3ba95
- **Merge commit**: 715723e
- **Date**: 2026-05-31

## Trigger
`/critic` — an isolated `critic` subagent adversarially reviewed the F10/F11 verification setup and
found the "zero prod impact" guarantee rested on conventions, not enforcement. Findings were
cross-verified against real code (one critic suggestion — adding `.dockerignore` — was rejected:
`.dockerignore` does not affect runtime bind mounts, only the build context).

## Findings → fixes (merged 715723e)
- **HIGH-1** — `verify smoke` only checked `paper=True` (a constant) + `broker.paper`; it never proved
  the keys belong to the intended TEST account, so pasting the prod *paper* account keys (the one the
  daemon trades) would pass silently. **Fix:** assert live `account_number == EXPECTED_ACCOUNT_NUMBER`
  (new key in `.env.test`, pinned `PA3F5JU0T43K`); FAIL CLOSED on mismatch, loud WARNING if unset.
  `scripts/verify.sh` smoke guard + `.env.test.example`.
- **HIGH-2** — "zero prod impact" relied on convention. `config.py:19` `ENV_FILE = os.environ.get(
  "AUTOSTOCK_ENV_FILE") or PROJECT_ROOT/".env"` is import-time; if the var is ever unset, or compose
  is run from the main root (prod `.env` bind-mounted at `/app/.env`), prod creds load. **Fix:**
  `verify.sh` `preflight()` fails closed if `AUTOSTOCK_ENV_FILE` unset/missing or `/app/.env` present.
- **MEDIUM** — compose set BOTH `env_file: [.env.test]` (injects OS env) AND `AUTOSTOCK_ENV_FILE`
  (pydantic dotenv). pydantic precedence = OS env > dotenv, so the file wasn't authoritative — a
  footgun if a host `ALPACA_*` leaked in. **Fix:** dropped `env_file`; app reads creds only via
  Settings (verified no raw `os.environ['ALPACA_*']`), so the dotenv stays the single source.
- **MEDIUM** — F11's cleanup covered only python writers; `typecheck` (bun/turbo/tsgo) still left
  root-owned `.turbo` (per-package), nested `packages/*/node_modules`, and `*.tsbuildinfo`. **Fix:**
  `verify.sh` EXIT-trap `cleanup()` (root → can delete) sweeps all of them.

## Verification (in-container, against the worktree)
- Positive: typecheck **0 root-owned leftovers**, unit **376**, smoke **matches pin PA3F5JU0T43K**.
- Negative (fail-closed): `AUTOSTOCK_ENV_FILE` unset → exit 1; account mismatch → exit 1.
- Worktree had an inited submodule → `git worktree remove` refuses; used `rm -rf` + `git worktree
  prune` (now sudo-free thanks to the clean tree). Recorded in [[worktree-live-verification]].

## Open / next iteration
- Full agent/command-surface smoke (AAPL-limit-order class) still TODO — best after [[F9]] (console
  Alpaca orders) merges. Tracked in [[F10]] state.

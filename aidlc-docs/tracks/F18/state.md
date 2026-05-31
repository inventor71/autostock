# Track F18 — docker-verify `attach` console-MCP env wiring

> Per-track state. Single writer = this track's worktree session. Lean hotfix to the F15
> attach harness (per [[feedback-registry-requires-track-record]] still gets a track record).

## Track Info
- **Track ID**: F18
- **Title**: docker-verify `attach` mode — wire the console MCP env (AUTOSTOCK_ROOT + shared token)
- **Type**: fix (verify-harness; F10→F11→F12→F15 lineage)
- **Status**: merged (→ main `8f5468c`, no-ff; base `6902612`, 2026-05-31)
- **Branch**: feat/F18
- **Worktree**: .claude/worktrees/F18
- **Submodule branch**: — (parent-repo `docker-compose.verify.yml` only)
- **Base commit**: 6902612 (main, post-F9)
- **Start Date**: 2026-05-31

## Problem (found while live-verifying F9 via attach)
F15's `attach` service in `docker-compose.verify.yml` sets only AUTOSTOCK_ENV_FILE/PYTHONPATH/
STEERING_DIR. But the opencode console MCP config (`operator-console/cli/.opencode/opencode.jsonc`)
substitutes `{env:AUTOSTOCK_ROOT}` (the `mcp-server.ts` command path) and
`{env:STEERING_OPERATOR_TOKEN}` (the shared daemon↔console secret, `runtime.py:51`). With neither
set in-container, the MCP command resolves to `/operator-console/...` (not `/app/...`) so the MCP
server never starts → **console order tools are absent in attach** (and the token would mismatch).
F15 only validated the daemon-boot probe, never the in-container console MCP path. See
[[f9-gated-alpaca-orders]], [[f4-steering-runtime-wiring]].

## Fix (minimal)
Add to the `attach` service `environment:` in `docker-compose.verify.yml`:
- `AUTOSTOCK_ROOT: /app`
- `STEERING_OPERATOR_TOKEN: ${STEERING_OPERATOR_TOKEN:-attach-test-token}` (host-overridable;
  TEST-only default so the in-container daemon + console share ONE token; container is the TEST
  paper account only — preflight forbids prod `.env`).

## Stage Progress (minimal depth)
- [x] Workspace Detection — brownfield; harness fix
- [x] Requirements — explicit (the env gap above); RE/stories/design/units SKIP (config glue)
- [ ] Construction — edit attach env (+2 lines) in the worktree
- [ ] Build & Test — `docker compose -f docker-compose.verify.yml config -q` + confirm rendered
      attach env carries both vars; (full attach MCP already proven live in the F9 worktree fix)
- [ ] Merge — feat/F18 → main; registry + audit one-liner

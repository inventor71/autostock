# Track F29 — Supervisor-mode codebase orientation (헷갈림·경로 혼선 개선)

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F29
- **Title**: Supervisor 모드에서 에이전트가 코드베이스 구조를 빠르게 파악하도록 개선 — 경로·구조 혼선 감소, 첫 턴부터 정확한 파일 읽기
- **Type**: feature
- **Status**: active (ready to merge)
- **Branch**: feat/F29
- **Worktree**: .claude/worktrees/F29
- **Submodule branch**: — (no submodule changes; gitlink updated to main's HEAD)
- **Base commit**: bb2da2d (actual: 4765e22 at worktree creation)
- **Start Date**: 2026-06-01T14:21:28Z
- **Completed**: 2026-06-02

## Stage Progress
- [x] Workspace Detection — brownfield; RE artifacts exist
- [x] Requirements Analysis — approved 2026-06-02
- [x] Workflow Planning — approved 2026-06-02
- [x] User Stories — SKIP
- [x] Application Design — SKIP
- [x] Units Generation — SKIP
- [x] Construction
  - [x] Functional Design — SKIP
  - [x] NFR Requirements — SKIP
  - [x] NFR Design — SKIP
  - [x] Infrastructure Design — SKIP
  - [x] Code Generation — complete (critic fixes applied)
  - [x] Build & Test — complete (docker-verify attach verified)
- [x] ALL STAGES COMPLETE

## Implementation Summary
- **6 files modified**, **1 file created** (tests), **1 file created** (docs)
- **Python**: `runtime.py` (_publish_codebase_tree + _walk_tree, depth=2, indent-aware, fnmatch), `channel.py` (publish_codebase)
- **TypeScript**: `parser.ts` (READ_VERBS + "codebase"), `steer-handler.ts` (/codebase dispatch), `filedrop.ts` (readCodebase), `mcp-server.ts` (steer_read description)
- **Tests**: `tests/test_codebase_tree.py` (11 tests), **574 total green**
- **0 new dependencies**, **0 F26 permission changes**

## Critic Fixes Applied
1. HIGH: Added `"codebase"` to parser READ_VERBS (was dead-on-arrival)
2. MEDIUM: Changed depth=1→2 with depth-aware indent for sub-packages
3. MEDIUM: Fixed `*.egg-info` exclusion via fnmatch glob
4. MEDIUM: Made `_REPO_ROOT` overridable via `root` parameter
5. Added 2 synthetic-tree tests for robust coverage

## Docker-Verify Verification (2026-06-02)
- steer_read{command:/codebase} → returns project tree with `/app` paths
- Key packages visible: src/agent/, src/risk/, operator-console/
- Build artifacts excluded: __pycache__, .git, node_modules
- Supervisor agent successfully uses tree for codebase orientation

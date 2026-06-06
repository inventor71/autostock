# Track R5 — `claude -p` headless invocation (investigate shared runner)

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: R5
- **Title**: Investigate sharing the `claude -p` subprocess/JSON-envelope handling
- **Type**: refactor (investigation-first)
- **Status**: backlog  <!-- not started -->
- **Branch**: refactor/R5 (TBD)
- **Worktree**: .claude/worktrees/R5 (TBD)
- **Submodule branch**: — (Python only)
- **Base commit**: ec2875c (survey point; rebase when picked up)
- **Start Date**: TBD

## Extension Configuration
- **Security Baseline**: Applicable — the agent path enables tools/Bash; do NOT widen the
  tool allowlist or permission surface while refactoring. The strategy path denies all tools —
  preserve that exactly. Verify no auth/key handling changes.
- **Property-Based Testing**: N/A.

## Scope
Two independent `claude` CLI wrappers exist:
- `src/strategy/llm/client.py::ClaudeCodeClient.complete()` — **single-shot, tools DISABLED**,
  neutral cwd, `--output-format json`, retry-with-backoff. Dev/backtest, avoids metered API key.
- `src/agent/session.py::AgentSession` — **tool-ENABLED, resumable** daily session, workspace cwd,
  permission modes, session-id-collision retry, injectable `runner`. The production agent path.

**They have genuinely different jobs** — do NOT force-merge the orchestration. The only safely
shareable bit is the low-level **run + JSON-envelope + returncode/error extraction**. This track is
investigation-first: confirm the overlap is worth a helper before extracting. See
`inception/refactor/claude-runner/guide.md`.

## Merge Risk Notes
- **공유 파일 (주의)**: `src/agent/session.py` is hot (agent path, touched by many F-tracks).
  Do this only when no agent-path track is active. `src/strategy/llm/client.py` is quieter.
- **API/시그니처 변경**: none public expected; only an internal helper.

## Stage Progress (skill: ai-dlc-refactor) — NOT STARTED
- [ ] Stage 0 — Investigation: measure real overlap; decide go/no-go (may close as "won't do")
- [ ] Stage 1 — Baseline + characterization (lean on `tests/test_agent.py`, `tests/test_llm_formatter.py`)
- [ ] Stage 2 — Tier ledger
- [ ] Stage 3 — Redesign (`run_claude_headless` / `parse_claude_json` signature)
- [ ] Stage 4 — Implementation
- [ ] Build & Test

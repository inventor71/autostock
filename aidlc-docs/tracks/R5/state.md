# Track R5 — `claude -p` headless invocation (investigate shared runner)

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: R5
- **Title**: Investigate sharing the `claude -p` subprocess/JSON-envelope handling
- **Type**: refactor (investigation-first)
- **Status**: closed — won't-do (Stage 0 investigation, 2026-06-07)  <!-- overlap ~12 lines in hot agent brain; cure > disease. See 0-investigation.md -->
- **Branch**: refactor/R5 (not yet branched — investigation-first)
- **Worktree**: .claude/worktrees/R5 (not yet created)
- **Submodule branch**: — (Python only)
- **Base commit**: 5e786b0 (main HEAD at pick-up)
- **Start Date**: 2026-06-06

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

## Stage Progress (skill: ai-dlc-refactor) — CLOSED at Stage 0
- [x] Stage 0 — Investigation: **go/no-go = NO-GO (won't-do)**. Real overlap ~12 lines (post-`subprocess.run`
      JSON-envelope), concentrated in the hot/high-stakes agent brain (`session.py`, F69 active). Agent
      retry couples to exact exception text (`_SESSION_ERROR_FRAGMENTS`) so a shared helper can only
      relocate — not simplify — the messages; strategy-only use = no dedup. Cure (touch trading brain +
      reproduce exact messages) > disease. Minimal `parse_claude_json` alternative documented but skipped.
      See `inception/refactor/claude-runner/0-investigation.md`.
- [~] Stage 1 — Baseline + characterization — N/A (closed at Stage 0)
- [~] Stage 2 — Tier ledger — N/A
- [~] Stage 3 — Redesign — N/A
- [~] Stage 4 — Implementation — N/A
- [~] Build & Test — N/A (no code change)

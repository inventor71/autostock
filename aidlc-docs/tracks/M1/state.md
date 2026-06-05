# Track M1 — AI-DLC concurrent multi-track customization

> Per-track state. Single writer = this session. See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: M1
- **Title**: AI-DLC concurrent multi-track customization (partition + worktree gate)
- **Type**: process/meta (applied directly on main per user; not a feature worktree)
- **Status**: active
- **Branch**: main (rule/command/doc edits only — no application code)
- **Worktree**: — (meta-work; worktree gate applies to application code, not rule edits)
- **Submodule branch**: —
- **Base commit**: 631ec6e
- **Start Date**: 2026-05-31

## Scope
Customize AI-DLC for a solo developer running multiple feature tracks concurrently. User chose
"full partition + worktree gate". Decided in chat 2026-05-31.

Root cause being fixed: shared single-file state (`aidlc-state.md`, `audit.md`) is written by
multiple concurrent track sessions → "file modified externally" races (observed live between
F7/F8, and again during this very session on `audit.md`).

## Decisions
- **Partition, don't lock.** One writer per file. Per-track `tracks/<id>/{state.md,audit.md}`.
- Root `aidlc-state.md` → **Track Registry** only. Root `audit.md` → global timeline, merge-time
  appends only (so this M1 work deliberately does NOT append to root audit.md mid-flight).
- **Worktree gate (blocking)**: no application code outside a worktree; submodule gets its own
  `feat/<track>` branch; parent gitlink committed only at merge.

## Stage Progress
- [x] New rule `common/concurrent-tracks.md`
- [x] `tracks/_TEMPLATE/{state.md,audit.md}`
- [x] `code-generation.md` worktree gate (Step 9.5) + track-file references
- [x] `CLAUDE.md` concurrent-tracks section + directory tree
- [x] Commands updated: ai-dlc-request, ai-dlc-resume, ai-dlc-status
- [x] Root `aidlc-state.md` Track Registry + migration note
- [x] Memory note (process decision) — `[[aidlc-multitrack-partition]]`
- [x] Verification bootstrap: `scripts/worktree-setup.sh <track> [--ts] [--py]` + concurrent-tracks
      "Verification bootstrap" section + worktree-live-verification memory TS half. Fixes the
      recurring "can't tsgo in the worktree" (root cause: bun not on PATH + node_modules absent;
      install is cheap with warm bun cache + hardlinks, not a network op).
- [ ] Optional follow-up: also wire refactor/deprecate commands + a track-merge helper (deferred)
- [x] CodeKB (`common/codekb.md`): shared codebase knowledge cache, single-writer = CI, ported
      from upstream `aidlc-workflows-concurrent`. Rule files updated (workspace-detection,
      reverse-engineering Step 0/12a, requirements-analysis Step 1, session-continuity,
      concurrent-tracks) + `.github/workflows/codekb-refresh.yml` (CI, `CLAUDE_CODE_OAUTH_TOKEN`).

## CodeKB Bootstrap
- [x] CodeKB bootstrapped by this track (seed under `aidlc-docs/codekb/`, 8 files)
- **Bootstrap SHA**: `58ca6a7dbbc3195fa5ca5f966b96a84bc2fd500a`
- **Bootstrap Date**: `2026-06-06`
- **Note**: seed reflects current HEAD (not the older M1 RE snapshot). After next push to `main`,
  CI (`codekb-refresh.yml`) becomes the sole writer.

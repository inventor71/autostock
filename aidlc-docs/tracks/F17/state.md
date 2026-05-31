# Track F17 — docker-verify cleanup: sudo-free teardown (ownership handback)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F17 (F14/F16 taken by the concurrent session, F15 merged)
- **Title**: docker-verify cleanup — hand bind-mount ownership back to the host (no sudo)
- **Type**: feature (verification-harness tooling; F10→F11→F12→F15 lineage)
- **Status**: merged (→ main `f912999`, 2026-05-31)
- **Branch**: feat/F17
- **Worktree**: .claude/worktrees/F17
- **Submodule branch**: — (parent-repo file only: `scripts/verify.sh`)
- **Base commit**: cc125e5
- **Start Date**: 2026-05-31T05:10:52Z

## Extension Configuration
- **Security Baseline**: Enabled — SECURITY-15 (the chown is fail-safe: guarded `|| true`, never
  aborts a run; preflight untouched). No secrets handled. Others N/A.
- **Property-Based Testing**: Disabled — one-line shell glue; validated by a container repro.

## Problem (root-caused, evidence)
Repeated docker-verify runs leave **root-owned files in the worktree** that require `sudo` to
clean up. The container runs as **root** (`Dockerfile.verify` has no `USER`), so anything it
writes into the bind-mounted worktree (`.:/app`) lands `root:root`; the host then can't unlink
it (you need write on the parent *directory*, which is root-owned). Two cases, only one needs sudo:
- **Empty mountpoint dirs** (`steering/ logs/ workspace/ node_modules/`) — docker auto-creates
  them root-owned, but they're empty ⇒ host-removable (write on parent suffices). Not the trigger.
- **Content-bearing root trees** — e.g. `attach`'s console wrote `operator-console/cli/.opencode/`
  with **3674 root-owned files** (measured on the F15 leftover) ⇒ sudo. This is whack-a-mole:
  F11 fixed python scratch, F12 fixed JS/turbo scratch, F15's attach added `.opencode/`.

## Fix (catch-all, not enumeration)
Add to `cleanup()` in `scripts/verify.sh` (runs as root at the EXIT/INT/TERM trap, so it CAN chown):
```sh
host_owner="$(stat -c '%u:%g' /app 2>/dev/null || echo 0:0)"   # /app's owner == host user (bind
find /app -xdev -exec chown "$host_owner" {} + 2>/dev/null || true  # mount preserves uid); -xdev
                                                                    # skips the named volumes
```
Self-discovering (no env): `/app`'s numeric owner in-container equals the host user (verified:
container saw uid 1000). `-xdev` keeps it on the bind mount, skipping the node_modules/steering/…
named volumes (different fs, not part of the worktree). Catches ANY future root-owned write, so
this is the last fix of this class. Keeps the existing per-path `rm -rf` lines (tidiness); the
chown is the safety net. Applies to all four modes (typecheck/unit/smoke/attach).

## Out of scope
- Pre-creating empty mountpoint dirs host-owned (they're already removable; cosmetic only).
- Running the container as the host UID (breaks fresh named-volume writes + ~/.claude/HOME).

## Stage Progress
- [x] Workspace Detection — brownfield; RE artifacts exist → RE skipped
- [x] Requirements Analysis — minimal; root-caused with evidence, user approved the fix
- [x] User Stories / App Design / Units — skip (one-line harness glue)
- [x] Construction — added ownership-handback to verify.sh `cleanup()` (chown bind mount → host owner)
- [x] Build & Test — `bash -n` OK; **faithful test**: real `cleanup()` (EXIT trap) turned a planted
      root-owned `.opencode/` (0:0 → 1000:989) and host `rm -rf` then succeeded WITHOUT sudo; real
      `verify typecheck` exit 0 "typecheck OK" leaving 0 root-owned content files (only the empty
      `node_modules` volume mountpoint, removable). Merged → main `f912999`.

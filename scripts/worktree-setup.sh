#!/usr/bin/env bash
# worktree-setup.sh — bootstrap an AI-DLC track worktree so it is *verifiable in place*.
#
# Why this exists: each git worktree gets its own checkout, and the submodule's
# node_modules (~2.8G) + the tsgo binary are gitignored build output that never lands
# in a fresh worktree — so `tsgo`/typecheck silently can't run and verification keeps
# getting deferred to "the user's machine". The fix is cheap: bun's global cache is warm
# (~2.6G) and bun's default backend is hardlinks, so `bun install --frozen-lockfile` in a
# worktree is a near-offline hardlink farm (seconds, ~no disk), NOT a network download.
# This also injects the main .env so live (paper-account) checks work from the worktree.
# See .aidlc-rule-details/common/concurrent-tracks.md and the worktree-live-verification memory.
#
# Usage:
#   scripts/worktree-setup.sh <track> [--ts] [--py]
#     <track>   track id / slug (e.g. F9, console-foo). Worktree = .claude/worktrees/<track>,
#               parent branch + submodule branch = feat/<track>.
#     --ts      TS submodule track: init submodule, branch it, bun install, verify tsgo.
#     --py      Python track: symlink the main .env into the worktree (pydantic loads it).
#
# Idempotent: re-running reuses an existing worktree/branch and re-checks deps.

set -euo pipefail

MAIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUBMODULE="operator-console/cli"
BUN_BIN="$HOME/.bun/bin"

die() { echo "ERROR: $*" >&2; exit 1; }
note() { echo "  • $*"; }

[ $# -ge 1 ] || die "usage: scripts/worktree-setup.sh <track> [--ts] [--py]"
TRACK="$1"; shift
DO_TS=0; DO_PY=0
for arg in "$@"; do
  case "$arg" in
    --ts) DO_TS=1 ;;
    --py) DO_PY=1 ;;
    *) die "unknown flag: $arg" ;;
  esac
done

BRANCH="feat/${TRACK}"
WT="${MAIN_ROOT}/.claude/worktrees/${TRACK}"

echo "▶ Track '${TRACK}' worktree bootstrap"
echo "  main:     ${MAIN_ROOT}"
echo "  worktree: ${WT}  (branch ${BRANCH})"

# 1) Parent-repo worktree -------------------------------------------------------
if [ -d "$WT" ]; then
  note "worktree exists — reusing"
else
  if git -C "$MAIN_ROOT" show-ref --verify --quiet "refs/heads/${BRANCH}"; then
    git -C "$MAIN_ROOT" worktree add "$WT" "$BRANCH"
  else
    git -C "$MAIN_ROOT" worktree add "$WT" -b "$BRANCH"
  fi
  note "worktree created"
fi

# 2) TS submodule: init + branch + install + verify tsgo ------------------------
if [ "$DO_TS" -eq 1 ]; then
  echo "▶ TS submodule (${SUBMODULE})"
  # init the submodule inside the worktree if not yet populated
  if [ ! -e "${WT}/${SUBMODULE}/package.json" ]; then
    note "initializing submodule in worktree"
    git -C "$WT" submodule update --init "$SUBMODULE"
  fi
  # branch the submodule (never leave it detached — concurrent-tracks rule)
  if git -C "${WT}/${SUBMODULE}" show-ref --verify --quiet "refs/heads/${BRANCH}"; then
    git -C "${WT}/${SUBMODULE}" switch "$BRANCH"
  else
    git -C "${WT}/${SUBMODULE}" switch -c "$BRANCH"
  fi
  note "submodule on ${BRANCH}"
  # ensure bun is on PATH (the recurring blocker: bun lives under ~/.bun/bin and a
  # bare shell doesn't have it — same class of issue as the daemon claude-CLI PATH bug)
  [ -x "${BUN_BIN}/bun" ] || die "bun not found at ${BUN_BIN}/bun — install bun or fix PATH"
  export PATH="${BUN_BIN}:${PATH}"
  note "bun $(bun --version) on PATH"
  # cache-warm, hardlinked install — cheap, near-offline
  ( cd "${WT}/${SUBMODULE}" && bun install --frozen-lockfile )
  if [ -x "${WT}/${SUBMODULE}/node_modules/.bin/tsgo" ]; then
    note "tsgo ready → typecheck:  (cd ${WT}/${SUBMODULE} && PATH=${BUN_BIN}:\$PATH bun run typecheck)"
  else
    die "tsgo still missing after install — check ${SUBMODULE}/package.json devDeps"
  fi
fi

# 3) Python track: inject main .env so get_settings() resolves in the worktree --
if [ "$DO_PY" -eq 1 ]; then
  echo "▶ Python env"
  if [ -e "${MAIN_ROOT}/.env" ]; then
    ln -sf "${MAIN_ROOT}/.env" "${WT}/.env"
    note "linked main .env → worktree (pydantic Settings will load it)"
  else
    note "no main .env to link (skipping)"
  fi
  note "run with main venv:  ${MAIN_ROOT}/venv/bin/python  (read-only calls only — see worktree-live-verification)"
fi

echo "✔ '${TRACK}' ready at ${WT}"

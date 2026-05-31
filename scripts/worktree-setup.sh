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
#   scripts/worktree-setup.sh <track> [--ts] [--py] [--docker-verify]
#     <track>          track id / slug (e.g. F9, console-foo). Worktree = .claude/worktrees/<track>,
#                      parent branch + submodule branch = feat/<track>.
#     --ts             TS submodule track: init submodule, branch it, bun install, verify tsgo.
#     --py             Python track: symlink the main .env into the worktree (pydantic loads it).
#     --docker-verify  Containerized verification (F10): init submodule on the HOST (the container
#                      can't — worktree .git is outside the mount) + provision .env.test (COPIED from
#                      ${MAIN_ROOT}/.env.test if present, else from the example), then print the
#                      `docker compose -f docker-compose.verify.yml` commands. ZERO prod impact:
#                      the container loads .env.test only (a TEST paper account), never prod .env.
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
DO_TS=0; DO_PY=0; DO_DOCKER_VERIFY=0
for arg in "$@"; do
  case "$arg" in
    --ts) DO_TS=1 ;;
    --py) DO_PY=1 ;;
    --docker-verify) DO_DOCKER_VERIFY=1 ;;
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
    note "F20: if this track adds Alpaca read tools, set ALPACA_API_KEY + ALPACA_API_SECRET in env before running MCP server"
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

# 4) Docker verification harness (F10): host-side prep the container can't do -----
if [ "$DO_DOCKER_VERIFY" -eq 1 ]; then
  echo "▶ Docker verification harness"
  [ -e "${WT}/docker-compose.verify.yml" ] || die \
    "docker-compose.verify.yml missing in ${WT} — the harness lives on feat/docker-verify; \
merge/rebase it into this track first."
  # Submodule must be initialized on the HOST: the worktree's .git is a pointer OUTSIDE the
  # mounted /app, so in-container `git submodule update` fails. typecheck needs these files.
  if [ ! -e "${WT}/${SUBMODULE}/package.json" ]; then
    note "initializing submodule on host (container can't reach the worktree .git)"
    git -C "$WT" submodule update --init "$SUBMODULE"
  else
    note "submodule already initialized"
  fi
  # Provision .env.test (TEST paper account). The canonical TEST creds live at the MAIN repo root
  # `${MAIN_ROOT}/.env.test` — reuse them by COPYING into the worktree (a symlink would dangle
  # inside the container, which mounts only the worktree). COPY, never the prod `.env` — that is the
  # whole isolation point. Fall back to the example template if no main .env.test exists yet.
  if [ -e "${WT}/.env.test" ]; then
    note ".env.test already present in worktree (reusing)"
  elif [ -e "${MAIN_ROOT}/.env.test" ]; then
    cp "${MAIN_ROOT}/.env.test" "${WT}/.env.test"
    note ".env.test copied from main (${MAIN_ROOT}/.env.test) — reusing the TEST paper account creds."
    note "  (gitignored in the worktree; prod .env is never used.)"
  else
    cp "${WT}/.env.test.example" "${WT}/.env.test"
    note ".env.test scaffolded from example — FILL IN the TEST paper account keys (or put them at"
    note "  ${MAIN_ROOT}/.env.test once and future tracks copy them automatically). gitignored."
  fi
  cat <<EOF
  ✔ ready. Run FROM the worktree dir (so .:/app mounts THIS worktree):
      cd ${WT}
      docker compose -f docker-compose.verify.yml build
      docker compose -f docker-compose.verify.yml run --rm verify typecheck
      docker compose -f docker-compose.verify.yml run --rm verify unit
      docker compose -f docker-compose.verify.yml run --rm verify smoke   # needs real TEST keys + ~/.claude
EOF
fi

echo "✔ '${TRACK}' ready at ${WT}"

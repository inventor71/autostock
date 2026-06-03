#!/usr/bin/env bash
# F27 — single entry point for the docker-verify harness. Runs the container as the HOST user
# (UID:GID) so every file the container writes onto the bind-mounted worktree is host-owned from
# the start. That removes the whole class of root-owned-file problems the harness used to paper
# over after the fact: `git worktree remove` needs no sudo, and in-container git no longer trips
# git's "dubious ownership" guard on the host-owned .git.
#
# Why a wrapper instead of compose interpolating $UID directly: bash's $UID is readonly AND not
# exported, so `${UID}` in compose resolves to empty; and a project-root .env (UID/GID) would be
# bind-mounted to /app/.env and trip verify.sh's prod-safety preflight. So we export DOCKER_UID /
# DOCKER_GID here and the compose file reads those (fail-loud `${DOCKER_UID:?...}` so a bypassed
# `docker compose` call fails with a clear message instead of silently using the wrong UID).
#
# Usage (replaces the old raw `docker compose -f docker-compose.verify.yml ...` invocations):
#   scripts/verify-run.sh build
#   scripts/verify-run.sh run --rm verify typecheck
#   scripts/verify-run.sh run --rm verify unit
#   scripts/verify-run.sh run --rm verify smoke      # needs real TEST keys + ~/.claude
#   scripts/verify-run.sh run --rm -it attach        # full daemon + console TUI (TEST account)
set -euo pipefail

# $UID is readonly in bash, so use distinct names. id(1) gives the real host UID/GID.
DOCKER_UID="$(id -u)"
DOCKER_GID="$(id -g)"
export DOCKER_UID DOCKER_GID

cd "$(dirname "$0")/.."   # run from the worktree root so `.:/app` mounts THIS worktree's code.

# Pre-create the named-volume mountpoint dirs as the HOST user. Docker's daemon (root) would
# otherwise create any missing mountpoint dir on the bind-mounted worktree owned root:root — an
# empty but root-owned residue (removable, since the parent is host-owned, but it defeats the
# "no root-owned anything" intent). Creating them here (we run as the host user) makes docker reuse
# the host-owned dirs. These paths mirror the volume mounts in docker-compose.verify.yml.
mkdir -p operator-console/cli/node_modules operator-console/node_modules \
         steering workspace logs 2>/dev/null || true

COMPOSE=(docker compose -f docker-compose.verify.yml)

# G-7: a freshly-created named volume is owned root:root, so the non-root container can't write
# into it (bun install → EACCES on the node_modules volumes). Before any real run, a one-shot ROOT
# helper (`init-perms`, the only service WITHOUT `user:`) chowns the volume mountpoints to the host
# UID:GID. Deterministic — unlike a Dockerfile chmod, it is not shadowed by the /app bind mount.
# Only needed for the run/up subcommands; build/config/etc. don't touch the volumes.
case "${1:-}" in
  run|up)
    "${COMPOSE[@]}" run --rm init-perms >/dev/null 2>&1 \
      || echo "[verify-run] warning: init-perms (volume chown) failed — first bun install may hit EACCES" >&2
    ;;
esac

exec "${COMPOSE[@]}" "$@"

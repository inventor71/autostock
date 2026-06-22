#!/usr/bin/env bash
# F90 — prod multi-instance runtime control. ONE entry point for running N agent daemons, each on
# its own (paper) account + workspace + aggressiveness, all from this single checkout. Mirrors the
# verify-run.sh pattern (host UID/GID injection, fail-loud) but for the REAL daemon, long-running.
#
# Usage:
#   scripts/prod-run.sh up      <name>          # start daemon in the background (account = .env.<name>)
#   scripts/prod-run.sh attach  <name>          # docker exec the operator console TUI into the daemon
#   scripts/prod-run.sh ls                      # list running instances (account · aggressiveness · status)
#   scripts/prod-run.sh logs    <name>          # follow the daemon log
#   scripts/prod-run.sh down    <name> [--wipe] # stop instance (--wipe also removes its state volumes)
#   scripts/prod-run.sh migrate <name> <src>    # one-time: copy host <src>/{workspace,steering} into the volumes
#
# Each instance needs config/.env.<name> (see config/.env.example) — git-ignored; it carries the
# account creds + AUTOSTOCK_AGGRESSIVENESS / AUTOSTOCK_BROKER_PROVIDER / STEERING_OPERATOR_TOKEN.
set -euo pipefail

cd "$(dirname "$0")/.."        # run from the repo root so `.:/app` mounts THIS checkout.
REPO="$PWD"
COMPOSE_FILE=docker-compose.prod.yml
IMAGE=autostock-verify:latest
ENV_DIR="config"               # per-instance env files live here: config/.env.<name>

DOCKER_UID="$(id -u)"; DOCKER_GID="$(id -g)"; export DOCKER_UID DOCKER_GID

die() { printf '\n\033[1;31m[prod-run] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }
log() { printf '\033[1;34m[prod-run]\033[0m %s\n' "$*" >&2; }

# Normal-mode console permission (steering files only; source reads blocked — same as verify attach).
CONSOLE_PERM='{"read":{"*":"deny","../../steering/**":"allow"},"glob":"deny","grep":"deny","lsp":"deny","external_directory":{"*":"deny","/app/steering/**":"allow"}}'

# Resolve + export everything an instance needs from config/.env.<name>. Sets globals:
#   INSTANCE, COMPOSE_PROJECT_NAME, ACCOUNT_ENV_HOST, AUTOSTOCK_ACCOUNT_ID,
#   AUTOSTOCK_AGGRESSIVENESS, AUTOSTOCK_BROKER_PROVIDER, STEERING_OPERATOR_TOKEN, TZ
load_instance() {
  INSTANCE="${1:?instance name required}"
  [[ "$INSTANCE" =~ ^[a-zA-Z0-9_-]+$ ]] || die "instance name must be [a-zA-Z0-9_-]: '$INSTANCE'"
  # Absolute path: docker-compose.prod.yml bind-mounts this at /run/account.env, and compose only
  # treats a volume source as a bind mount (not a named volume) when it's absolute or ./-prefixed.
  ACCOUNT_ENV_HOST="$REPO/$ENV_DIR/.env.$INSTANCE"
  [ -f "$ACCOUNT_ENV_HOST" ] || die "$ENV_DIR/.env.$INSTANCE not found — copy $ENV_DIR/.env.example and fill it."

  # Read AUTOSTOCK_* / account selectors from the file WITHOUT exporting the account secrets into
  # our own env (the daemon reads them via AUTOSTOCK_ENV_FILE inside the container). Grep the keys.
  get() { grep -E "^${1}=" "$ACCOUNT_ENV_HOST" | tail -1 | cut -d= -f2- | sed 's/^["'\'']//;s/["'\'']$//'; }
  AUTOSTOCK_AGGRESSIVENESS="$(get AUTOSTOCK_AGGRESSIVENESS)"
  AUTOSTOCK_BROKER_PROVIDER="$(get AUTOSTOCK_BROKER_PROVIDER)"
  STEERING_OPERATOR_TOKEN="$(get STEERING_OPERATOR_TOKEN)"
  [ -n "$STEERING_OPERATOR_TOKEN" ] || STEERING_OPERATOR_TOKEN="prod-$INSTANCE-token"  # local default

  # Account identity for the SR-1 dedup label — never the raw secret. account_farm has an explicit
  # BROKER_ACCOUNT_ID; alpaca uses a short non-reversible digest of the API key id.
  local acct_id alpaca_key
  acct_id="$(get BROKER_ACCOUNT_ID)"
  if [ -z "$acct_id" ]; then
    alpaca_key="$(get ALPACA_API_KEY)"
    [ -n "$alpaca_key" ] && acct_id="alpaca-$(printf '%s' "$alpaca_key" | sha256sum | cut -c1-12)"
  fi
  [ -n "$acct_id" ] || die "$ACCOUNT_ENV_HOST has neither BROKER_ACCOUNT_ID nor ALPACA_API_KEY."
  AUTOSTOCK_ACCOUNT_ID="$acct_id"

  COMPOSE_PROJECT_NAME="autostock-$INSTANCE"
  export INSTANCE COMPOSE_PROJECT_NAME ACCOUNT_ENV_HOST AUTOSTOCK_ACCOUNT_ID \
         AUTOSTOCK_AGGRESSIVENESS AUTOSTOCK_BROKER_PROVIDER STEERING_OPERATOR_TOKEN
}

compose() { docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT_NAME" "$@"; }

ensure_image() {
  docker image inspect "$IMAGE" >/dev/null 2>&1 && return
  log "image '$IMAGE' missing — building once via the verify Dockerfile (a few minutes)…"
  docker compose -f docker-compose.verify.yml build verify || die "image build failed"
}

cmd_up() {
  load_instance "${1:-}"
  ensure_image

  # SR-1: refuse if ANOTHER running instance already trades this account (double-execution guard).
  local clash
  clash="$(docker ps --filter "label=autostock.account=$AUTOSTOCK_ACCOUNT_ID" \
            --format '{{.Label "autostock.instance"}}' | grep -vx "$INSTANCE" || true)"
  [ -z "$clash" ] || die "account '$AUTOSTOCK_ACCOUNT_ID' is already traded by instance '$clash' — \
one daemon per account (would double-execute). Stop it first or use a different BROKER_ACCOUNT_ID."

  # SR-2: warn if a HOST daemon (non-container) is running — it may share this account.
  if pgrep -af "python.*main.py.*--mode agent" | grep -vq docker >/dev/null 2>&1; then
    log "WARNING: a host 'main.py --mode agent' process appears to be running. If it trades the same"
    log "         account as '$INSTANCE', stop it first to avoid double execution. (Ctrl-C to abort.)"
    sleep 4
  fi

  log "init-perms (volume chown) + starting daemon '$INSTANCE' (account $AUTOSTOCK_ACCOUNT_ID, \
aggressiveness ${AUTOSTOCK_AGGRESSIVENESS:-<settings.yaml>})…"
  compose run --rm init-perms >/dev/null || log "warning: init-perms failed — first write may EACCES"
  compose up -d daemon
  log "up. Watch: scripts/prod-run.sh logs $INSTANCE   |   Console: scripts/prod-run.sh attach $INSTANCE"
}

cmd_attach() {
  load_instance "${1:-}"
  local cid; cid="$(compose ps -q daemon)"
  [ -n "$cid" ] || die "instance '$INSTANCE' is not running — start it: scripts/prod-run.sh up $INSTANCE"
  log "attaching operator console to '$INSTANCE' (daemon keeps running after you quit the console)…"
  # The exec inherits the daemon container's env (AUTOSTOCK_ROOT, STEERING_DIR, STEERING_OPERATOR_TOKEN,
  # AUTOSTOCK_LOCKDOWN). We add the normal-mode read permission + bun on PATH.
  docker exec -it \
    -e OPENCODE_PERMISSION="$CONSOLE_PERM" \
    -e PATH=/usr/local/bun/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    "$cid" bash -lc 'cd /app/operator-console/cli/packages/opencode && exec bun run dev'
}

cmd_ls() {
  printf '%-16s %-26s %-14s %-10s %s\n' INSTANCE ACCOUNT AGGRESSIVENESS STATUS CONTAINER
  docker ps -a --filter "label=autostock.instance" \
    --format '{{.Label "autostock.instance"}}\t{{.Label "autostock.account"}}\t{{.Label "autostock.aggressiveness"}}\t{{.State}}\t{{.Names}}' \
    | sort | while IFS=$'\t' read -r inst acct aggr state name; do
        printf '%-16s %-26s %-14s %-10s %s\n' "$inst" "$acct" "$aggr" "$state" "$name"
      done
}

cmd_logs() { load_instance "${1:-}"; local cid; cid="$(compose ps -q daemon)"; \
  [ -n "$cid" ] || die "instance '$INSTANCE' not running"; docker logs -f "$cid"; }

cmd_down() {
  load_instance "${1:-}"
  if [ "${2:-}" = "--wipe" ]; then
    log "stopping '$INSTANCE' AND removing its state volumes (workspace/steering/logs) — irreversible."
    compose down -v
  else
    log "stopping '$INSTANCE' (state volumes preserved; re-up resumes its memory)."
    compose down
  fi
}

cmd_migrate() {
  load_instance "${1:-}"
  local src="${2:?usage: migrate <name> <host-src-dir containing workspace/ and steering/>}"
  [ -d "$src/workspace" ] || die "$src/workspace not found"
  # Don't clobber: target workspace volume must be empty.
  compose run --rm init-perms >/dev/null || true
  if [ -n "$(docker run --rm -v "${COMPOSE_PROJECT_NAME}_workspace":/v "$IMAGE" sh -c 'ls -A /v 2>/dev/null')" ]; then
    die "instance '$INSTANCE' workspace volume is NOT empty — refusing to overwrite. (down --wipe first if intended.)"
  fi
  # SR-2: the source host daemon must be stopped before copying (avoid copying a live-mutating tree).
  log "Copying $src/{workspace,steering} → instance '$INSTANCE' volumes. Ensure the host daemon for this"
  log "account is STOPPED (Ctrl-C within 4s to abort)…"; sleep 4
  docker run --rm -v "${COMPOSE_PROJECT_NAME}_workspace":/dest -v "$REPO/$src/workspace":/src:ro \
    "$IMAGE" sh -c 'cp -a /src/. /dest/ 2>/dev/null || true'
  [ -d "$src/steering" ] && docker run --rm -v "${COMPOSE_PROJECT_NAME}_steering":/dest -v "$REPO/$src/steering":/src:ro \
    "$IMAGE" sh -c 'cp -a /src/. /dest/ 2>/dev/null || true'
  log "migrated. Start it: scripts/prod-run.sh up $INSTANCE"
}

case "${1:-}" in
  up)      cmd_up "${2:-}" ;;
  attach)  cmd_attach "${2:-}" ;;
  ls)      cmd_ls ;;
  logs)    cmd_logs "${2:-}" ;;
  down)    cmd_down "${2:-}" "${3:-}" ;;
  migrate) cmd_migrate "${2:-}" "${3:-}" ;;
  *) cat >&2 <<EOF
prod-run.sh — F90 prod multi-instance control
  up <name> | attach <name> | ls | logs <name> | down <name> [--wipe] | migrate <name> <src>
Each instance reads config/.env.<name> (copy config/.env.example).
EOF
     exit 2 ;;
esac

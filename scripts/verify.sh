#!/usr/bin/env bash
# F10 verification harness entrypoint. Runs inside the verify container (see docker-compose.verify.yml).
# Modes:  all | typecheck | unit | smoke | attach   (passed as the run arg; default `all`).
#
#   typecheck — operator-console (bun) typecheck against the mounted console source.
#   unit      — deterministic offline pytest (in-test doubles; never calls the real LLM/Alpaca).
#   smoke     — REAL claude + read-only Alpaca on the TEST account; asserts it is NOT prod. No orders.
#   all       — typecheck + unit  (smoke is opt-in: it needs real test keys + the claude mount).
#   attach    — F15: FULL runtime for a human to watch. Runs the daemon (main.py --mode agent
#               --steering) in the background + the operator console TUI in the foreground, both on
#               the TEST paper account. Same wiring as prod EXCEPT the account (and no systemd — the
#               daemon is a plain bg process here). REAL claude + REAL Alpaca paper TEST endpoint;
#               the daemon may place PAPER orders on the TEST account. Use the `attach` compose
#               service (it adds tty + ~/.claude:rw + runtime volumes):
#                 docker compose -f docker-compose.verify.yml run --rm -it attach
#
# Hard rule (zero prod impact): everything here loads `.env.test` via AUTOSTOCK_ENV_FILE. The
# preflight() below FAILS CLOSED rather than trusting that convention — it refuses to run if the
# env-file override is unset/missing, or if a production `.env` got bind-mounted into /app (which
# happens if you run compose from the main repo root instead of a worktree).
#
# NOTE on git: this runs in a git-worktree whose `.git` points OUTSIDE the /app mount, so in-container
# `git` fails. The console source ships in the checkout; only the gitignored node_modules/tsgo are
# absent and are installed by `bun install` below — no in-container git is needed.
set -euo pipefail

MODE="${1:-all}"
CONSOLE_DIR="operator-console/cli"

log()  { printf '\n\033[1;36m[verify:%s]\033[0m %s\n' "$MODE" "$*"; }
fail() { printf '\n\033[1;31m[verify:%s] FAIL:\033[0m %s\n' "$MODE" "$*" >&2; exit 1; }

# Console deps live in a SHARED node_modules volume (docker-compose.verify.yml: fixed-name external
# volume, host-owned via init-perms). `bun install` populates it on the FIRST run (slow, once,
# global) and is FAST afterward (warm store → it only re-creates the per-package workspace symlinks
# under operator-console/cli/packages/*/node_modules, which the runtime bind mount otherwise hides).
# Run as the host user → writes the shared volume without EACCES.
ensure_console_deps() {
  local dir="$1"
  log "bun install in $dir (shared node_modules volume — slow only on the first ever run, then fast)"
  ( cd "$dir" && bun install --frozen-lockfile )
}

# preflight — enforce the isolation invariant instead of assuming it (critic HIGH-2). The container
# runs as root; if any of these are wrong, a run could silently load the production account.
preflight() {
  # 1) The env-file override MUST be set and point at an existing file. If it were empty, config.py
  #    falls back to PROJECT_ROOT/.env (= /app/.env, the bind mount) — exactly the prod file we avoid.
  [ -n "${AUTOSTOCK_ENV_FILE:-}" ] || fail \
    "AUTOSTOCK_ENV_FILE is unset — refusing to run (config.py would fall back to /app/.env = prod)."
  [ -f "$AUTOSTOCK_ENV_FILE" ]    || fail \
    "AUTOSTOCK_ENV_FILE=$AUTOSTOCK_ENV_FILE does not exist — fill the TEST .env.test first."
  # 2) A production .env must NOT be present in the mount. Its presence usually means compose was run
  #    from the main repo root (prod .env bind-mounted at /app/.env), not a worktree — fail closed.
  #    EXCEPTION: `attach` copies .env.test → /app/.env (the daemon + MCP server both read .env),
  #    leaving an identical copy on the worktree that would otherwise block the next run. Allow
  #    /app/.env only when it is byte-identical to .env.test; a real prod .env differs → still refused.
  if [ -e /app/.env ] && ! cmp -s /app/.env /app/.env.test; then
    fail "/app/.env exists and differs from .env.test — you ran compose from a dir containing a prod
     .env (run it FROM the verify worktree, which has only .env.test). Refusing for prod safety."
  fi
}

# F27 — no cleanup/chown-handback. The container now runs as the HOST user (compose `user:`,
# injected by scripts/verify-run.sh), so every file it writes into the bind-mounted worktree is
# host-owned from the start: `git worktree remove` needs no sudo, and there is nothing root-owned
# to sweep or chown back. (The old F17 cleanup() that ran on EXIT was deleted with this change.)
# Build scratch (.pyc, hypothesis DB) is still kept off /app via the compose env knobs for tidiness.

run_typecheck() {
  log "operator-console typecheck (bun)"
  [ -f "$CONSOLE_DIR/package.json" ] || fail \
    "$CONSOLE_DIR/package.json missing — the worktree checkout is incomplete or corrupt."
  ensure_console_deps "$CONSOLE_DIR"
  ( cd "$CONSOLE_DIR" && bun run typecheck )
  log "typecheck OK"
}

run_unit() {
  log "pytest (deterministic / offline)"
  # -p no:cacheprovider → no .pytest_cache written into the bind-mounted worktree (root-owned junk
  # the host then can't delete). Bytecode + hypothesis are redirected off /app via env (see compose).
  PYTHONPATH=/app pytest -q -p no:cacheprovider
  log "unit OK"
}

run_smoke() {
  log "REAL claude + read-only Alpaca on the TEST account (no orders)"

  # 1) Real LLM path: prove the host ~/.claude login is reachable through the mount.
  claude --version || fail "claude CLI not available"

  # 2) Read-only Alpaca on the TEST account. `paper=True` only selects the paper ENDPOINT — it does
  #    NOT prove the keys belong to the intended TEST account (you could paste the prod *paper*
  #    account keys the daemon trades). So we ASSERT account_number == EXPECTED_ACCOUNT_NUMBER from
  #    .env.test and fail closed on mismatch (critic HIGH-1). EXPECTED_ACCOUNT_NUMBER is a non-pydantic
  #    key, so read it straight from the env file rather than from Settings.
  PYTHONPATH=/app python - <<'PY'
import os, sys
from config.config import get_settings
from alpaca.trading.client import TradingClient

def env_file_value(key):
    path = os.environ.get("AUTOSTOCK_ENV_FILE", "")
    try:
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and line.split("=", 1)[0].strip() == key:
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""

s = get_settings()
if not s.alpaca_api_key or not s.alpaca_api_secret:
    sys.exit("smoke: ALPACA keys empty in .env.test — fill the TEST paper account keys first.")
if not s.broker.paper:
    sys.exit("smoke: broker.paper is False — refusing to run smoke against a non-paper account.")

expected = env_file_value("EXPECTED_ACCOUNT_NUMBER")
client = TradingClient(s.alpaca_api_key, s.alpaca_api_secret, paper=True)
acct = client.get_account()  # read-only
print(f"  account id     : {acct.id}")
print(f"  account number : {acct.account_number}")
print(f"  status         : {acct.status}")
print(f"  equity         : {acct.equity}")
if expected:
    if acct.account_number != expected:
        sys.exit(f"smoke: account_number {acct.account_number} != EXPECTED_ACCOUNT_NUMBER "
                 f"{expected} — these keys are NOT the pinned TEST account. Refusing (prod safety).")
    print(f"  >> OK: matches pinned EXPECTED_ACCOUNT_NUMBER ({expected}).")
else:
    print("  >> WARNING: EXPECTED_ACCOUNT_NUMBER not set in .env.test — cannot prove this is the")
    print("     TEST account. Pin it (e.g. EXPECTED_ACCOUNT_NUMBER=PA...) to fail closed on a wrong key.")
PY
  log "smoke OK (read-only; no orders placed)"
  log "TODO next iteration: full agent/command-surface smoke (e.g. AAPL limit-buy via console)."
}

# F15 — attach: full runtime (daemon + console TUI) for a human to watch the live sidebar.
# Same as prod except the account is the TEST paper account. Requires the `attach` compose
# service (tty + ~/.claude:rw + steering/workspace/logs volumes). The daemon writes its runtime
# state ONLY into those named volumes (/app/steering, /app/workspace, /app/logs), so nothing
# root-owned lands in the bind-mounted worktree.
run_attach() {
  [ -f "$CONSOLE_DIR/package.json" ] || fail \
    "$CONSOLE_DIR/package.json missing — the worktree checkout is incomplete or corrupt."
  claude --version >/dev/null 2>&1 || fail \
    "claude CLI not reachable — the daemon's LLM turns need the host ~/.claude mounted (rw)."

  : "${STEERING_DIR:=/app/steering}"; export STEERING_DIR
  mkdir -p "$STEERING_DIR" /app/logs

  # F22: copy .env.test → .env so both the Python daemon (pydantic-settings default)
  # and the TS MCP server (alpaca-data.ts dotenv fallback) find the test keys without
  # needing ALPACA_* OS-env vars (those would override the dotenv file and break auth).
  # A worktree-setup.sh symlink .env → main .env is dangling in the container; remove first.
  rm -f /app/.env
  cp /app/.env.test /app/.env
  log "copied .env.test → .env (daemon + MCP server both read .env)"

  # F27 — removed: the `git config --global --add safe.directory '*'` workaround. The container runs
  # as the HOST user now, so git no longer flags the host-owned mounted repo as dubious-ownership;
  # no safe.directory is needed. The attach path runs no in-container git at all.

  # Console deps are baked in the image + seeded into the volumes; normally a no-op here.
  ensure_console_deps "$CONSOLE_DIR"
  # F22: mcp-server.ts lives at operator-console/src/ and its deps (@modelcontextprotocol/sdk,
  # zod) are declared in operator-console/package.json — a separate node_modules from cli/, so the
  # MCP SDK import resolves (else the MCP server exits and the console shows -32000).
  ensure_console_deps "/app/operator-console"

  log "starting daemon: main.py --mode agent --steering  (TEST paper account; .env=.env.test copy)"
  ( cd /app && unset AUTOSTOCK_ENV_FILE && PYTHONPATH=/app exec python -u main.py --mode agent --steering ) \
      > /app/logs/daemon.attach.log 2>&1 &
  DAEMON_PID=$!
  # F27: stop the daemon on ANY exit (normal quit, Ctrl-C, error). No .git restore and no cleanup
  # chown sweep anymore — the container is the host user, so there is nothing root-owned to undo.
  trap 'log "stopping daemon (pid $DAEMON_PID)"; kill "$DAEMON_PID" 2>/dev/null || true; \
        wait "$DAEMON_PID" 2>/dev/null || true' EXIT INT TERM

  log "waiting for the first snapshot ($STEERING_DIR/snapshot.json) — up to 180s (a startup LLM turn can be slow)…"
  for i in $(seq 1 180); do
    [ -f "$STEERING_DIR/snapshot.json" ] && { log "snapshot published after ${i}s"; break; }
    if ! kill -0 "$DAEMON_PID" 2>/dev/null; then
      log "daemon exited before publishing a snapshot — last 40 log lines:"
      tail -n 40 /app/logs/daemon.attach.log 2>/dev/null || true
      fail "daemon failed to start (see above). Usual causes: bad/empty TEST keys in .env.test, or claude not logged in."
    fi
    sleep 1
  done
  if [ ! -f "$STEERING_DIR/snapshot.json" ]; then
    log "no snapshot after 180s — last 40 daemon log lines:"; tail -n 40 /app/logs/daemon.attach.log 2>/dev/null || true
    fail "daemon never published a snapshot (wedged?). Inspect /app/logs/daemon.attach.log."
  fi

  log "launching the operator console TUI — the live sidebar is below. Quit (or Ctrl-C) stops the daemon too."

  # F26: if AUTOSTOCK_SUPERVISOR=on is set (from the compose env or host override), build and
  # inject the supervisor permission profile. Container paths are fixed: AUTOSTOCK_ROOT=/app,
  # STEERING_DIR=/app/steering, consoleCwd=/app/operator-console/cli (worktree-relative for
  # read patterns). Normal mode: MCP+web+$STEERING_DIR only. Supervisor: whole /app except secrets.
  if [ "${AUTOSTOCK_SUPERVISOR:-}" = "on" ]; then
    log "SUPERVISOR mode — injecting full /app read permission (secrets/logs/.git excluded)"
    # read patterns are worktree-relative (consoleCwd=/app/operator-console/cli → steering=../../steering)
    OPENCODE_PERMISSION='{"read":{"*":"allow",".env*":"deny","**/.env*":"deny","*.key":"deny","*.pem":"deny","secrets/**":"deny","**/secrets/**":"deny","logs/**":"deny","**/logs/**":"deny",".git/**":"deny","**/.git/**":"deny"},"glob":"allow","grep":"allow","lsp":"allow","external_directory":{"*":"deny","/app/**":"allow","/app/secrets/**":"deny","/app/logs/**":"deny","/app/.git/**":"deny"}}'
    export OPENCODE_PERMISSION
  else
    # Normal mode (default): MCP+web tools + only $STEERING_DIR readable. glob/grep/lsp off.
    log "NORMAL mode — steering files only; source reads blocked"
    OPENCODE_PERMISSION='{"read":{"*":"deny","../../steering/**":"allow"},"glob":"deny","grep":"deny","lsp":"deny","external_directory":{"*":"deny","/app/steering/**":"allow"}}'
    export OPENCODE_PERMISSION
  fi

  ( cd "$CONSOLE_DIR/packages/opencode" && exec bun run dev )
}

preflight
case "$MODE" in
  typecheck) run_typecheck ;;
  unit)      run_unit ;;
  smoke)     run_smoke ;;
  attach)    run_attach ;;
  all)       run_typecheck; run_unit
             log "‘all’ done (typecheck+unit). Run mode 'smoke' separately for the real-LLM/account check." ;;
  *)         fail "unknown mode '$MODE' (use: all | typecheck | unit | smoke | attach)" ;;
esac

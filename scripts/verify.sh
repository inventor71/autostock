#!/usr/bin/env bash
# F10 verification harness entrypoint. Runs inside the verify container (see docker-compose.verify.yml).
# Modes:  all | typecheck | unit | smoke | attach   (passed as the run arg; default `all`).
#
#   typecheck — operator-console (bun) typecheck against the mounted submodule source.
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
# `git` fails. We therefore NEVER run `git submodule update` here — the submodule must be initialized
# on the HOST before building/running (the script errors clearly if its files are absent).
set -euo pipefail

MODE="${1:-all}"
CONSOLE_DIR="operator-console/cli"

log()  { printf '\n\033[1;36m[verify:%s]\033[0m %s\n' "$MODE" "$*"; }
fail() { printf '\n\033[1;31m[verify:%s] FAIL:\033[0m %s\n' "$MODE" "$*" >&2; exit 1; }

# preflight — enforce the isolation invariant instead of assuming it (critic HIGH-2). The container
# runs as root; if any of these are wrong, a run could silently load the production account.
preflight() {
  # 1) The env-file override MUST be set and point at an existing file. If it were empty, config.py
  #    falls back to PROJECT_ROOT/.env (= /app/.env, the bind mount) — exactly the prod file we avoid.
  [ -n "${AUTOSTOCK_ENV_FILE:-}" ] || fail \
    "AUTOSTOCK_ENV_FILE is unset — refusing to run (config.py would fall back to /app/.env = prod)."
  [ -f "$AUTOSTOCK_ENV_FILE" ]    || fail \
    "AUTOSTOCK_ENV_FILE=$AUTOSTOCK_ENV_FILE does not exist — fill the TEST .env.test first."
  # 2) A production .env must NOT be present in the mount. Its presence means compose was run from the
  #    main repo root (prod .env bind-mounted at /app/.env), not a worktree — fail closed.
  if [ -e /app/.env ]; then
    fail "/app/.env exists in the container — you ran compose from a dir containing a prod .env
     (run it FROM the verify worktree, which has only .env.test). Refusing for prod safety."
  fi
}

# cleanup — the container runs as root, so any build/test scratch it writes into the bind-mounted
# worktree lands root:root and the host then can't `git worktree remove` without sudo. The compose
# env knobs stop the python writers; this trap also clears the JS toolchain's root-owned output
# (turbo cache, nested workspace node_modules) plus a defensive sweep. Runs as root → deletes fine.
cleanup() {
  rm -rf /app/.pytest_cache /app/.hypothesis 2>/dev/null || true
  # turbo writes a `.turbo` dir in EVERY package; bun writes per-package node_modules onto the bind
  # mount (the top-level node_modules is the masking volume = empty host mountpoint, host-removable).
  # Both are root-owned build output → clear so `git worktree remove` needs no sudo.
  find "/app/${CONSOLE_DIR}" -name .turbo -type d -prune -exec rm -rf {} + 2>/dev/null || true
  find "/app/${CONSOLE_DIR}/packages" -name node_modules -type d -prune -exec rm -rf {} + 2>/dev/null || true
  # tsgo/tsc incremental build info, written per-package, root-owned.
  find "/app/${CONSOLE_DIR}" -name '*.tsbuildinfo' -type f -exec rm -f {} + 2>/dev/null || true
  find /app/src /app/tests /app/config -name __pycache__ -type d \
    -exec rm -rf {} + 2>/dev/null || true
  # F17 — catch-all so teardown never needs sudo. The rm sweeps above enumerate KNOWN scratch, but
  # each new tool adds a new root-owned path (F11 python caches → F12 turbo/tsgo → F15 attach's
  # `.opencode/`, 3674 files). Instead of chasing them, hand EVERYTHING we wrote into the bind mount
  # back to the host user: the container runs as root, so this trap (also root) can chown freely.
  # /app's own numeric owner == the host user (bind mounts preserve uid) → discover it with stat, no
  # env needed. `-xdev` stays on the bind mount, skipping the node_modules/steering/… named volumes
  # (separate fs, not part of the worktree, and irrelevant to `git worktree remove`).
  local host_owner
  host_owner="$(stat -c '%u:%g' /app 2>/dev/null || echo 0:0)"
  find /app -xdev -exec chown "$host_owner" {} + 2>/dev/null || true
}
trap cleanup EXIT

run_typecheck() {
  log "operator-console typecheck (bun)"
  [ -f "$CONSOLE_DIR/package.json" ] || fail \
    "submodule not initialized: $CONSOLE_DIR/package.json missing. Init it on the HOST first:
     git -C <main-repo> submodule update --init <worktree>/$CONSOLE_DIR
     (in-container git can't do this — the worktree .git lives outside the mount)."
  ( cd "$CONSOLE_DIR" && bun install --frozen-lockfile && bun run typecheck )
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
if not s.alpaca_api_key or not s.alpaca_secret_key:
    sys.exit("smoke: ALPACA keys empty in .env.test — fill the TEST paper account keys first.")
if not s.broker.paper:
    sys.exit("smoke: broker.paper is False — refusing to run smoke against a non-paper account.")

expected = env_file_value("EXPECTED_ACCOUNT_NUMBER")
client = TradingClient(s.alpaca_api_key, s.alpaca_secret_key, paper=True)
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
    "submodule not initialized: $CONSOLE_DIR/package.json missing — init it on the HOST first
     (scripts/worktree-setup.sh <track> --docker-verify)."
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

  # The worktree submodule .git can be a pointer (gitdir:) that escapes the /app bind
  # mount, breaking in-container git. Swap in a throwaway standalone repo for the
  # container — but NON-DESTRUCTIVELY: the bind mount is the HOST worktree, so a plain
  # `rm .git` here clobbers the host submodule's git metadata (F22 + F25 both got bitten:
  # branch reset to an empty `master`, history lost). Move the host .git aside and restore
  # it in the EXIT trap. (A self-contained standalone .git dir passes rev-parse and is left
  # untouched.)
  # First, tell the container's git (running as root) to TRUST the host-owned
  # mounted repos. Without this, git 2.36+ flags "dubious ownership" and every
  # `git` call fails — which would trip the standalone-repo case below into the
  # mv-aside path needlessly (and that path's restore is best-effort: a killed
  # container leaves the host .git as a root-owned `master` snapshot). With the
  # repo trusted, a self-contained standalone .git just works and is left alone.
  git config --global --add safe.directory '*' 2>/dev/null || true

  CONSOLE_GIT="${CONSOLE_DIR}/.git"
  CONSOLE_GIT_RESTORE=0
  # ONLY act when .git is a FILE (a worktree gitdir: pointer that escapes the /app
  # mount). A standalone .git DIRECTORY is a real self-contained repo — never touch
  # it, even if rev-parse hiccups, so we can't clobber it into a `master` snapshot
  # (the recurring F22/F25 data-loss bug). [-f] not [-e] is the load-bearing guard.
  if [ -f "$CONSOLE_GIT" ] && ! git -C "${CONSOLE_DIR}" rev-parse --git-dir >/dev/null 2>&1; then
    log "fixing submodule .git for container (non-destructive — host .git restored on exit)"
    mv "$CONSOLE_GIT" "${CONSOLE_GIT}.hostbak"
    ( cd "${CONSOLE_DIR}" && git init -q && git add -A && git commit -q -m "container snapshot" --allow-empty ) 2>/dev/null || true
    CONSOLE_GIT_RESTORE=1
  fi

  log "installing console deps (bun) — first run only, cached in the node_modules volume"
  ( cd "$CONSOLE_DIR" && bun install --frozen-lockfile )
  # F22: mcp-server.ts lives at operator-console/src/ and its deps (@modelcontextprotocol/sdk,
  # zod) are declared in operator-console/package.json. The cli/ install only populates
  # cli/node_modules — a separate install at the operator-console level is needed so bun can
  # resolve the MCP SDK import (else the MCP server exits and the console shows -32000).
  ( cd /app/operator-console && bun install --frozen-lockfile )

  log "starting daemon: main.py --mode agent --steering  (TEST paper account; .env=.env.test copy)"
  ( cd /app && unset AUTOSTOCK_ENV_FILE && PYTHONPATH=/app exec python -u main.py --mode agent --steering ) \
      > /app/logs/daemon.attach.log 2>&1 &
  DAEMON_PID=$!
  # Stop the daemon, restore the host submodule .git, and clear root-owned scratch on ANY
  # exit (normal quit, Ctrl-C, error). Overrides the bare `trap cleanup EXIT` set above.
  trap 'log "stopping daemon (pid $DAEMON_PID)"; kill "$DAEMON_PID" 2>/dev/null || true; \
        wait "$DAEMON_PID" 2>/dev/null || true; \
        [ "${CONSOLE_GIT_RESTORE:-0}" = 1 ] && { rm -rf "$CONSOLE_GIT"; mv "${CONSOLE_GIT}.hostbak" "$CONSOLE_GIT"; }; \
        cleanup' EXIT INT TERM

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

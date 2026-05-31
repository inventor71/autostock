#!/usr/bin/env bash
# F10 verification harness entrypoint. Runs inside the verify container (see docker-compose.verify.yml).
# Modes:  all | typecheck | unit | smoke   (passed as the run arg; default `all`).
#
#   typecheck — operator-console (bun) typecheck against the mounted submodule source.
#   unit      — deterministic offline pytest (in-test doubles; never calls the real LLM/Alpaca).
#   smoke     — REAL claude + read-only Alpaca on the TEST account; asserts it is NOT prod. No orders.
#   all       — typecheck + unit  (smoke is opt-in: it needs real test keys + the claude mount).
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

preflight
case "$MODE" in
  typecheck) run_typecheck ;;
  unit)      run_unit ;;
  smoke)     run_smoke ;;
  all)       run_typecheck; run_unit
             log "‘all’ done (typecheck+unit). Run mode 'smoke' separately for the real-LLM/account check." ;;
  *)         fail "unknown mode '$MODE' (use: all | typecheck | unit | smoke)" ;;
esac

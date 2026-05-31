#!/usr/bin/env bash
# F10 verification harness entrypoint. Runs inside the verify container (see docker-compose.verify.yml).
# Modes:  all | typecheck | unit | smoke   (passed as the run arg; default `all`).
#
#   typecheck — operator-console (bun) typecheck against the mounted submodule source.
#   unit      — deterministic offline pytest (in-test doubles; never calls the real LLM/Alpaca).
#   smoke     — REAL claude + read-only Alpaca on the TEST account; asserts it is NOT prod. No orders.
#   all       — typecheck + unit  (smoke is opt-in: it needs real test keys + the claude mount).
#
# Hard rule (zero prod impact): everything here loads `.env.test` via AUTOSTOCK_ENV_FILE. There is
# no path to the production `.env` or account from inside this container.
#
# NOTE on git: this runs in a git-worktree whose `.git` points OUTSIDE the /app mount, so in-container
# `git` fails. We therefore NEVER run `git submodule update` here — the submodule must be initialized
# on the HOST before building/running (the script errors clearly if its files are absent).
set -euo pipefail

MODE="${1:-all}"
CONSOLE_DIR="operator-console/cli"

log()  { printf '\n\033[1;36m[verify:%s]\033[0m %s\n' "$MODE" "$*"; }
fail() { printf '\n\033[1;31m[verify:%s] FAIL:\033[0m %s\n' "$MODE" "$*" >&2; exit 1; }

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
  PYTHONPATH=/app pytest -q
  log "unit OK"
}

run_smoke() {
  log "REAL claude + read-only Alpaca on the TEST account (no orders)"

  # 1) Real LLM path: prove the host ~/.claude login is reachable through the mount.
  claude --version || fail "claude CLI not available"

  # 2) Read-only Alpaca on the TEST account; assert it is a PAPER account and surface its id so a
  #    human can eyeball that it is the TEST account, never prod.
  PYTHONPATH=/app python - <<'PY'
import sys
from config.config import get_settings
from alpaca.trading.client import TradingClient

s = get_settings()
if not s.alpaca_api_key or not s.alpaca_secret_key:
    sys.exit("smoke: ALPACA keys empty in .env.test — fill the TEST paper account keys first.")
if not s.broker.paper:
    sys.exit("smoke: broker.paper is False — refusing to run smoke against a non-paper account.")

client = TradingClient(s.alpaca_api_key, s.alpaca_secret_key, paper=True)
acct = client.get_account()  # read-only
print(f"  account id     : {acct.id}")
print(f"  account number : {acct.account_number}")
print(f"  status         : {acct.status}")
print(f"  equity         : {acct.equity}")
print("  >> CONFIRM the above is the TEST account, not production.")
PY
  log "smoke OK (read-only; no orders placed)"
  log "TODO next iteration: full agent/command-surface smoke (e.g. AAPL limit-buy via console)."
}

case "$MODE" in
  typecheck) run_typecheck ;;
  unit)      run_unit ;;
  smoke)     run_smoke ;;
  all)       run_typecheck; run_unit
             log "‘all’ done (typecheck+unit). Run mode 'smoke' separately for the real-LLM/account check." ;;
  *)         fail "unknown mode '$MODE' (use: all | typecheck | unit | smoke)" ;;
esac

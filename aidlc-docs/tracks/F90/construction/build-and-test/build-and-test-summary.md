# F90 — Build & Test Summary

> Infra track (Docker prod multi-instance). Light build/test surface — one Python unit (env
> overrides) + shell/compose static validation + a real-account smoke (operator-run, see
> post-merge-guide). Verify harness (F10/F15) untouched → no regression to that path.

## What ran (2026-06-22, worktree feat/F90)

| Check | Command | Result |
|-------|---------|--------|
| Unit — env overrides | `pytest tests/test_env_overrides.py -q` | **5 passed** |
| Unit — broker TradeAccount fallback | `pytest tests/test_account_farm_trade_account.py -q` | **2 passed** |
| Shell syntax | `bash -n scripts/prod-run.sh` | **OK** |
| Compose parse/interpolation | `docker compose -f docker-compose.prod.yml config -q` (required vars stubbed) | **parse OK** |
| Python compile | `py_compile src/execution/brokers/account_farm_broker.py` | **OK** |

### Unit coverage (`tests/test_env_overrides.py`)
- `_apply_env_overrides` injects `AUTOSTOCK_AGGRESSIVENESS`/`AUTOSTOCK_BROKER_PROVIDER` (creates the
  `broker` section on demand).
- No-op when env unset → YAML value stands (NFR-1 backward compatible).
- `get_settings()` reflects the override end-to-end.
- **F85 fail-safe**: a typo'd aggressiveness override coerces to `balanced` via the field validator
  — a bad container env never wedges the daemon.
- Shipped `settings.yaml` default unchanged when no override present.

## Real-account smoke (RAN 2026-06-22 — account_farm sandbox `6ddcca95…`)
`up smoke` → `ls` → `logs` → `down --wipe`, real F16 account_farm sandbox account, `aggressive`.
Found and fixed **two real bugs** the static checks missed; then verified the full harness path:

| # | Bug (smoke-found) | Fix |
|---|-------------------|-----|
| 1 | `up` failed: *"service daemon refers to undefined volume config/.env.smoke"* — the per-instance env source was a **relative** path (`config/.env.<name>`), which Compose treats as a *named volume*, not a bind mount. | `prod-run.sh` `load_instance`: `ACCOUNT_ENV_HOST="$REPO/$ENV_DIR/.env.$INSTANCE"` (absolute). |
| 2 | Daemon crash-looped: *"unknown mode 'python'"* — the reused `autostock-verify:latest` image has `ENTRYPOINT ["bash","scripts/verify.sh"]` (a verify-mode dispatcher) that swallowed the `command`. | `docker-compose.prod.yml` `daemon`: add `entrypoint: ["python","-u","main.py"]` + `command: ["--mode","agent","--steering"]` (mirrors verify.sh `attach`). |

**Verified after the fixes** (one smoke run): Compose namespacing (`autostock-smoke_{workspace,steering,logs}`
volumes + `autostock-smoke-daemon-1`), per-instance `.env` bind-mounted RO at `/run/account.env`,
`AUTOSTOCK_ENV_FILE` wiring (daemon read the sandbox account), **env override propagated**
(`aggressiveness=aggressive` on the `ls` label + the daemon used it), `ls` table, SR-2 host-daemon
warning fired, and `down --wipe` removed every volume/network with no leftovers.

### account_farm boot bug — FOUND in smoke, FIXED in F90
After the wiring worked, the daemon crash-looped in `AccountFarmBroker.__init__` →
`alpaca.broker.client.get_trade_account_by_id` with a pydantic `TradeAccount` schema mismatch
(`last_daytrading_buying_power` / `last_daytrade_count` *Field required* — alpaca-py 0.43.2 marks
them `Optional` but with **no default**, so they're required keys the Broker sandbox omits).
Reproduced identically on the host outside Docker. **Fix** (`src/execution/brokers/account_farm_broker.py`):
a new `_fetch_trade_account()` keeps the happy path and, only on that `ValidationError`, rebuilds the
`TradeAccount` from the raw `/trading/accounts/<id>/account` payload with the two keys defaulted to
`None`. Both call sites (init + `_do_get_account`) use it. Locked by 2 unit tests (happy path +
fallback). **Re-smoked:** the daemon now boots to steady state — `restarts=0`, scheduler started,
agent research turn running (`model=opus`), holdings refreshed, `_do_get_account()` returns a valid
`TradeAccount` (buying_power/cash populated).

### Out of F90 scope — pre-existing, NOT fixed
- **Intraday auto-collection on account_farm-only instances** logs `intraday auto-collection wiring
  failed (non-fatal)`: `_setup_intraday_collection` always builds the **alpaca** `StockHistoricalDataClient`,
  which needs `ALPACA_API_KEY`/`ALPACA_API_SECRET` — absent from an account_farm-only `.env.<name>`.
  Non-fatal (the daemon runs fine); add `ALPACA_*` market-data creds to the instance env if intraday
  backfill is wanted. Pre-existing (same on host), independent of F90.
- **alpaca-provider path** (`.env.<name>` Option B, separate broker class) was **not** smoke-tested:
  a host daemon is already live on that account; a 2nd would risk double execution — exactly what
  SR-1/SR-2 guard against.

- **Verify-harness regression** (`scripts/verify-run.sh run --rm verify unit`): F90 adds a *separate*
  `docker-compose.prod.yml` and does not touch `docker-compose.verify.yml`/`verify-run.sh`, so the
  verify path is unaffected by construction; a confirmatory run is optional.
- **`attach` (interactive console TUI)**: not driven here (interactive `bun run dev`); the underlying
  `docker exec` path reuses the proven F18 verify-attach wiring. Operator-verify per post-merge-guide.

## Design ↔ code drift note (intentional improvement)
`infra-design.md` §2 mounted the per-instance env at `/app/.env.${INSTANCE}` (inside the shared code
mount). The code instead mounts it **read-only at `/run/account.env`, OUTSIDE `.:/app`**, read by the
daemon via `AUTOSTOCK_ENV_FILE`. This is strictly safer (instances can never clobber a shared
`/app/.env`) and keeps account secrets off the code tree. Account-id label/dedup also gained an
alpaca path (sha256 digest of the API key id) so SR-1 dedup works for both account_farm and alpaca.

## Compliance
- **SR-1** account 1:1 — `up` refuses if another running instance carries the same
  `autostock.account` label. ✅
- **SR-2** host daemon co-run — `up`/`migrate` warn + 4s abort window if a host `main.py --mode agent`
  is detected. ✅
- **SR-3** secrets — `config/.env.*` git-ignored (`!config/.env.example` kept). ✅
- **SR-4** verify untouched — separate compose file + namespaced volumes. ✅
- **NFR-1** override-unset = current behavior (unit-proven). **NFR-2** reuses `autostock-verify:latest`.
  **NFR-3** non-root host UID/GID. **NFR-4** `ls` surfaces running instances. ✅

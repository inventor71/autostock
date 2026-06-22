# F90 — Post-Merge Guide (Docker prod multi-instance)

> Audience: the operator (you), on `main` after merge. F90 adds a way to run **N real agent daemons
> at once** — each on its own paper account + workspace + aggressiveness — from this single checkout,
> and to `attach` the operator console into any of them. Reuses the verify toolchain image; the
> verify harness itself is unchanged.

## What changes on `main`
- **NEW `docker-compose.prod.yml`** — the real long-running daemon (`python main.py --mode agent
  --steering`), per-instance state in named volumes, isolation via `COMPOSE_PROJECT_NAME=autostock-<name>`.
- **NEW `scripts/prod-run.sh`** — `up | attach | ls | logs | down [--wipe] | migrate`.
- **NEW `config/.env.example`** — template for per-instance `config/.env.<name>` (git-ignored).
- **`config/config.py`** — `get_settings()` now overlays `AUTOSTOCK_AGGRESSIVENESS` /
  `AUTOSTOCK_BROKER_PROVIDER` from env onto the YAML before building `Settings`. **Unset → identical
  to before** (host runs and the verify harness are unaffected).
- **`.gitignore`** — ignores `config/.env.*` except `config/.env.example`.

## Prerequisites
- Docker + `docker compose`; WSL2 ok.
- The verify image `autostock-verify:latest` — `prod-run.sh up` auto-builds it via
  `docker-compose.verify.yml` if missing (a few minutes, one time).
- The warm external console volumes (`autostock-verify-cli-node-modules`,
  `autostock-verify-mcp-node-modules`) — created the first time you ran the verify `attach` harness.
  If you've never run verify attach, run it once so those external volumes exist.
- Real-LLM auth at `~/.claude` (bind-mounted rw for the daemon's session cache).

## First instance — step by step
1. **Create the account env** (git-ignored):
   ```
   cp config/.env.example config/.env.aggressive
   # fill BROKER_API_KEY / BROKER_API_SECRET / BROKER_ACCOUNT_ID (DISTINCT per instance),
   # set AUTOSTOCK_AGGRESSIVENESS=aggressive, AUTOSTOCK_BROKER_PROVIDER=account_farm
   ```
2. **(optional) migrate existing memory** — only if this instance should inherit a host book:
   ```
   scripts/prod-run.sh migrate aggressive .     # copies ./workspace + ./steering into the volumes
   ```
   Stop the host daemon for that account first (the script warns + gives a 4s abort window).
3. **Start it:** `scripts/prod-run.sh up aggressive`
4. **Watch logs:** `scripts/prod-run.sh logs aggressive`
5. **Open the console (TUI):** `scripts/prod-run.sh attach aggressive`
   — runs inside the daemon container; quitting the console leaves the daemon running.
6. **Add more instances:** repeat with a different name + a **different** `BROKER_ACCOUNT_ID`.

## Real-usage verification checklist (run once after merge)
- [ ] `scripts/prod-run.sh up <name>` returns "up." with no error.
- [ ] `scripts/prod-run.sh ls` lists the instance with its account + aggressiveness + `running`.
- [ ] `scripts/prod-run.sh logs <name>` shows the daemon booting and entering the steering loop;
      confirm **the aggressiveness in the log matches `.env.<name>`** (proves the env override path).
- [ ] `scripts/prod-run.sh attach <name>` opens the operator console; it can read steering data but
      **not** source files (normal-mode permission); the order book / account is the right one.
- [ ] **SR-1 guard:** try `up <name2>` with the *same* `BROKER_ACCOUNT_ID` while the first runs →
      it must **refuse** (no double-execution).
- [ ] `scripts/prod-run.sh down <name>` stops it; `ls` shows it stopped; re-`up` resumes memory
      (volumes preserved). `down --wipe <name>` removes its state volumes (irreversible).
- [ ] Host daemon / verify harness still behave exactly as before (override unset = no change).

Where to look: daemon stdout via `logs`; instance volumes are `autostock-<name>_workspace|steering|logs`;
container is `autostock-<name>-daemon-1`.

## Tuning knobs
- **Aggressiveness** per instance — `AUTOSTOCK_AGGRESSIVENESS` in `.env.<name>` (F85: conservative |
  balanced | aggressive; typo → balanced fail-safe).
- **Broker** — `AUTOSTOCK_BROKER_PROVIDER` (account_farm | alpaca). account_farm uses
  `BROKER_ACCOUNT_ID`; alpaca uses `ALPACA_API_*` (its dedup id is a sha256 digest of the key id).
- **Console secret** — `STEERING_OPERATOR_TOKEN` per instance; omitted → `prod-<name>-token` default.
- **Timezone** — `TZ` (default `Asia/Seoul`).

## Rollback
- Stop instances: `scripts/prod-run.sh down <name>` (add `--wipe` to drop volumes).
- The feature is additive: deleting/ignoring `docker-compose.prod.yml` + `scripts/prod-run.sh` and
  leaving the `AUTOSTOCK_*` env unset returns to pre-F90 behavior. The `config.py` change is a no-op
  when the env vars are absent.

## Known limits / out of scope
- **Intraday auto-collection needs `ALPACA_*` market-data creds.** An account_farm-only instance logs
  `intraday auto-collection wiring failed (non-fatal)` at boot — the intraday collector always uses the
  alpaca data provider, which needs `ALPACA_API_KEY`/`ALPACA_API_SECRET` (not the `BROKER_*` creds).
  The daemon runs fine without it; add `ALPACA_*` to `config/.env.<name>` if you want intraday backfill
  on that instance. Pre-existing behavior, unrelated to F90.
- **account_farm boot bug was fixed in this track.** `AccountFarmBroker` now tolerates the Broker
  sandbox `TradeAccount` schema (alpaca-py 0.43.x marks two daytrade fields required but the sandbox
  omits them) — verified: a farm-account daemon boots to a steady scheduler + agent loop.
- **One daemon per account** is enforced only across *containers* (label dedup) and *warned* for host
  processes — it can't see daemons on other machines. Keep `BROKER_ACCOUNT_ID` distinct per instance.
- No orchestration/restart-policy beyond `restart: unless-stopped`; no remote/network exposure (local
  Docker only).
- `migrate` is a one-time copy into an **empty** volume (refuses to overwrite); it does not sync.
- Console attach depends on the shared external verify node_modules volumes; if you prune those,
  re-run the verify attach harness once to recreate them.

# Infrastructure Design

## Deployment Model

- **Platform**: Local workstation or any Linux server; no cloud-specific infrastructure (no
  CDK, Terraform, or CloudFormation). The daemon and console run as long-lived processes
  managed by systemd `--user` units, optionally containerized via Docker Compose for
  production multi-instance deployments.
- **Orchestration**: Docker Compose (`docker-compose.prod.yml` for production,
  `docker-compose.verify.yml` for the deterministic/attach test harness); no Kubernetes.
  `scripts/prod-run.sh` and `scripts/verify-run.sh` wrap `docker compose` with instance
  namespacing and host-UID injection.

## Stacks & Resources

### Production Runtime (`docker-compose.prod.yml`)
- **Purpose**: Runs one or more independent daemon instances, each trading its own account
  (or its own `account_farm` sub-account), sharing a single verify-toolchain image and
  Node.js dependency volumes.
- **Key Resources**:
  - `init-perms` — one-shot root helper that chowns named volumes (`workspace`, `steering`,
    `logs`) to the host UID:GID before the daemon starts (Docker creates named volumes as
    root:root by default).
  - `daemon` — the production agent runtime; image `autostock-verify:latest` (shared, not
    rebuilt per project); runs as `${DOCKER_UID}:${DOCKER_GID}` (non-root); entrypoint
    `python -u main.py --mode agent --steering`; `restart: unless-stopped`; labeled with
    `autostock.instance` / `autostock.account` / `autostock.aggressiveness` for the SR-1
    account-dedup check.
  - Volumes: `.:/app` (shared code, read-mostly), `${HOME}/.claude:/tmp/.claude:rw` (LLM
    session/auth cache), `${ACCOUNT_ENV_HOST}:/run/account.env:ro` (per-instance credentials,
    deliberately mounted outside `/app` so instances can never clobber each other's
    credentials), named per-instance volumes `workspace`/`steering`/`logs`, and two external
    shared volumes `verify-node-modules`/`mcp-node-modules` (~2.8GB of console dependencies
    reused across every instance and worktree).
- **Defined In**: `docker-compose.prod.yml`, `scripts/prod-run.sh`

### Verification Harness (`docker-compose.verify.yml`, `Dockerfile.verify`)
- **Purpose**: Deterministic offline CI-style testing plus a full-runtime, human-observable
  "attach" mode against a dedicated TEST brokerage account.
- **Key Resources**:
  - `init-perms` — same permission-fix pattern as production.
  - `verify` — dispatches `typecheck` (bun), `unit` (pytest), or `all`; reads
    `AUTOSTOCK_ENV_FILE: /app/.env.test`; preflight asserts `.env.test` exists and — if a real
    `/app/.env` is also present — is byte-identical to it (prevents an accidental prod-account
    test run).
  - `attach` — runs the real daemon + console TUI together on the TEST account with a fixed
    `STEERING_OPERATOR_TOKEN=attach-test-token` (safe because it's test-only), foreground
    daemon + background console.
  - `seed-timeline` — populates a workspace volume with synthetic turns/interventions to
    exercise the console's timeline UI without waiting for real trading activity.
  - `Dockerfile.verify` base image: `python:3.12-slim` + git/curl/build-essential/nodejs +
    globally installed `@anthropic-ai/claude-code` CLI + Bun + all `pyproject.toml`
    dependencies (including the `dev` group) + a world-writable `/tmp` for arbitrary
    container UIDs. Console `node_modules` are deliberately **not** baked into the image
    (Bun's isolated-workspace symlinks would be shadowed by the runtime bind mount, or a
    root-owned baked copy would break non-root `bun install`); they live in the shared
    external volumes instead, populated at first run.
- **Defined In**: `docker-compose.verify.yml`, `Dockerfile.verify`, `scripts/verify.sh`,
  `scripts/verify-run.sh`

### Operator Console Deployment (`operator-console/launcher/`)
- **Purpose**: Installs and manages the human-facing TUI and its systemd-managed daemon
  companion outside of Docker, for a local/bare-metal single-instance setup.
- **Key Resources**:
  - `install.ts` — creates a `~/.local/bin/autostock` shim (bakes `AUTOSTOCK_ROOT`) and
    installs two systemd `--user` units (enabled + linger, so they survive logout).
  - `autostock-daemon.service` — `ExecStart=python main.py --mode agent --steering`,
    `WorkingDirectory=$AUTOSTOCK_ROOT` (`.env` loading is CWD-relative), `Restart=on-failure`.
  - `autostock-serve.service` (F71) — `ExecStart=~/.local/bin/autostock serve`, headless
    opencode server bound to the Tailscale interface only, password-gated
    (`OPENCODE_SERVER_PASSWORD`).
  - `daemon.ts` — health/wedge detection: watches `snapshot.json`'s `published_at` for
    staleness (45s window, more patient than the 5s publish cadence to absorb slow LLM
    turns); auto-restarts once on a detected wedge.
- **Defined In**: `operator-console/launcher/{cli,config,install,daemon,serve,unit-template,preflight}.ts`

## Environment Topology

| Environment | Account/Region | Purpose |
|---|---|---|
| Local dev (bare process) | Alpaca paper (US) or KIS paper (KR) | Day-to-day development, single instance |
| Verify (`docker-compose.verify.yml`) | Dedicated `.env.test` TEST account (pinned `EXPECTED_ACCOUNT_NUMBER`) | Deterministic unit/typecheck CI plus human-observable "attach" smoke runs; never touches the prod account |
| Production, single instance | `.env` at repo root, Alpaca or KIS paper/live | Default single-account deployment via systemd units |
| Production, multi-instance (F90) | `config/.env.<name>` per instance, `account_farm` sub-accounts or separate Alpaca accounts | Runs N agent instances concurrently (e.g. different aggressiveness settings or accounts) via `COMPOSE_PROJECT_NAME` namespacing |
| Mobile / remote | Tailscale tailnet, HTTPS via Tailscale cert | Phone PWA dashboard + WebAuthn-gated remote steering, fronted by `tailscale serve` on top of the local `opencode serve` (API) and `vite` (PWA) processes |

## Configuration & Secrets

- **Precedence**: CLI args > environment variables > `.env` (or `config/.env.<name>` for a
  named production instance, or `.env.test` under the verify harness) > `config/settings.yaml`
  > code defaults. Nested keys use `__` (e.g. `RISK__STOP_LOSS_PCT=0.03`). F90 adds two
  narrow env-var overrides applied on top of everything else:
  `AUTOSTOCK_AGGRESSIVENESS` → `agent.aggressiveness`, `AUTOSTOCK_BROKER_PROVIDER` →
  `broker.provider` (`config/config.py`, `_apply_env_overrides`).
- **settings.yaml top-level sections**: `app`, `broker` (name/paper/provider), `data`
  (provider/cache_dir/timeframe), `trading` (mode/batch interval), `risk` (position limits,
  stop/take-profit, short overrides F54/F60, market-halt thresholds, F85 aggressiveness),
  `backtest`, `monitoring` (alerts, health publish interval), `llm` (provider/model/
  temperature/prompt_version), `agent` (model, timeouts, min trade notional), `multi_agent`,
  `intraday` / `intraday_collection` (F3/F82), `surge` (F47), `signals` (movers,
  read-through, earnings/IPO F78, sentiment F77, disclosed holdings F81), `research`,
  `benchmark` (F70), `early_session`.
- **Secrets handling**: API keys and tokens (`ALPACA_API_KEY`/`ALPACA_API_SECRET`,
  `BROKER_ACCOUNT_ID`, `FINNHUB_API_KEY`, `STEERING_OPERATOR_TOKEN`,
  `OPENCODE_SERVER_PASSWORD`, `AUTOSTOCK_WEBAUTHN_ORIGIN`) come only from the environment or
  a gitignored `.env`/`config/.env.<name>` file — never committed and never hard-coded.
  gitleaks runs as a pre-commit hook (`.pre-commit-config.yaml`, `.gitleaks.toml`) with an
  explicit allowlist for `*.env.example` templates and known test fixtures.

## CI/CD

- **Pipeline**: GitHub Actions.
- **CodeKB Refresh** (`.github/workflows/codekb-refresh.yml`): triggers on every push to
  `main` (ignoring changes under `aidlc-docs/codekb/**` to avoid a self-triggering loop) or
  manually via `workflow_dispatch`. A cooldown gate requires at least 4 hours since the last
  bot-authored refresh commit, unless the code change since the last CodeKB baseline exceeds
  3% of `src/*.py` lines, in which case it proceeds immediately. The refresh step runs the
  headless `claude -p` CLI (subscription auth) with a restricted tool set
  (`Bash,Read,Edit,Write,Glob,Grep`) executing this same Reverse Engineering procedure, writes
  output under `aidlc-docs/codekb/`, and commits/pushes back to `main` as
  `codekb-ci[bot]` with message `docs: codekb refresh (<sha>)` — only if there are actual
  diffs.
- **Config Location**: `.github/workflows/`
- **Build tooling**: Python packaged via `hatchling` (PEP 517) from `pyproject.toml`
  (entry point `autostockd = "main:main"`); dependencies include `alpaca-py`, `yfinance`,
  `ta`, `apscheduler`, `pydantic`/`pydantic-settings`, `pyyaml`, `loguru`, `rich`, `plotly`,
  `pandas`/`pyarrow` (intraday Parquet feature store), `anthropic`, `openai`,
  `python-kis`; dev group adds `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `hypothesis`,
  `pre-commit`. Tests marked `manual` (real-LLM calls) are excluded from the default pytest
  run (`-m manual` opts in). The operator console uses a Bun workspace (typecheck via
  `bun run typecheck`).

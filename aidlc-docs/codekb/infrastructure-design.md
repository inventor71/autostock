# Infrastructure Design

## Deployment Model

- **Platform**: Single-node process (developer machine / server); no cloud-native deployment owned by this project; all cloud dependencies are external SaaS APIs (Alpaca, KIS, Anthropic, Finnhub)
- **Runtime**: Python 3.11+ CLI/daemon (`autostockd` entry point from `main.py`); TypeScript/Bun for operator console
- **Orchestration**: In-process APScheduler (`TradingScheduler`) — interval ticks + US-market cron for pre-market/intraday/EOD turns; no external orchestrator (no Kubernetes/ECS/Lambda)
- **Agent brain**: local `claude` CLI invoked as a subprocess; requires CLI installed and authenticated on the host

## Stacks & Resources

### Python Daemon (`autostockd`)
- **Purpose**: Main trading daemon — backtest / paper / live / agent modes
- **Key Resources**: Python 3.11+ process, `workspace/` file system for state (JSONL logs + journal), `.env` for credentials
- **Defined In**: `main.py`, `pyproject.toml` (entry point: `autostockd = "main:main"`)
- **Startup**: `autostockd --mode agent --steering` or `python main.py --mode <mode>`

### Operator Console (`operator-console/`)
- **Purpose**: Human-steering TUI for the agent daemon — system-tray app (macOS/Linux)
- **Key Resources**: Node/Bun process, `~/.local/bin/autostock` CLI symlink, file-drop IPC channel (`steering/` dir in workspace)
- **Defined In**: `operator-console/launcher/cli.ts`, built with Bun
- **Startup**: `autostock` CLI (installed by launcher); communicates with daemon via file-drop

### Verification Harness (Docker)
- **Purpose**: CI integration test environment — isolated Python + Node + Claude Code CLI
- **Key Resources**: Docker image (`Dockerfile.verify`), Docker Compose (`docker-compose.verify.yml`), bind-mounted repo, test `.env.test`
- **Services**:
  - `main`: verification runner (host UID, HOME=/tmp, `AUTOSTOCK_ENV_FILE=/app/.env.test`)
  - `init-perms`: one-shot `chown` of `/tmp/.claude` to host UID (F27 non-root runtime)
- **Volumes**: repo bind-mount (`.:/app`), `.claude` auth bind-mount (read-only), shared `node_modules_shared`

### CodeKB CI Refresh (GitHub Actions)
- **Purpose**: Automated reverse-engineering and CodeKB refresh on every push to `main`
- **Key Resources**: GitHub Actions runner, `claude -p` CLI (headless subscription token), bot committer (`codekb-ci`)
- **Defined In**: `.github/workflows/codekb-refresh.yml`
- **Trigger**: Push to `main` (excludes `aidlc-docs/codekb/**` to prevent refresh loops); `workflow_dispatch`
- **Cooldown Logic**:
  - Default: skip if last CodeKB refresh < 4 hours ago (`COOLDOWN_SECONDS=14400`)
  - Major-change override: if src code changed > 3% of lines, bypass cooldown regardless
- **Auth**: `CLAUDE_CODE_OAUTH_TOKEN` secret (subscription token); `GITHUB_TOKEN` with content-write permission
- **Output**: Commits fresh `aidlc-docs/codekb/` artifacts to `main` with message `docs: codekb refresh (<short-sha>)`

## Environment Topology

| Environment | Account/Region | Purpose |
|---|---|---|
| Development | Local machine, Alpaca paper account | Feature development, manual testing |
| Test / CI | Docker container, separate Alpaca paper account (`.env.test`) | Automated integration tests; F10 isolates from dev paper account |
| Paper trading | Alpaca paper API / KIS 모의투자 | Strategy validation before live; no real fills |
| Live trading | Alpaca live API / KIS 실전 (pending) | Real-money execution (opt-in via config + live keys) |
| Broker API sandbox | Alpaca Broker API sandbox | Account farm development and multi-account testing |
| Backtest | Local SimulatedBroker | Offline bar replay; no external API calls |

## CI/CD

- **Pipeline**: GitHub Actions (`inventor71/autostock`)
- **Config Location**: `.github/workflows/codekb-refresh.yml`
- **Verify Harness**: `scripts/verify.sh` — Docker Compose integration tests against TEST account
- **Test Runner**: pytest; `asyncio_mode=auto`; `@pytest.mark.manual` deselected by default (skips real LLM calls)
- **Worktree Gate**: `.claude/hooks/guard-main-edits.py` (PreToolUse) blocks app-code edits on `main` while any AI-DLC track is active; allowlist: `aidlc-docs/`, `.aidlc-rule-details/`, `*.md`; override: `AUTOSTOCK_ALLOW_MAIN_EDIT=1`
- **No Auto-Deploy**: Live trading requires manual operator initiation — no automated deployment pipeline

## File System State Layout

```
<workspace>/
├── decisions.jsonl            # Agent brain → body hand-off (append-only, cursor-indexed)
├── execution_log.jsonl        # Decision → fill audit ledger
├── turn_log.jsonl             # Per-turn metadata (cost, duration)
├── trades_log.jsonl           # Closed round-trip P&L
├── equity_log.jsonl           # Portfolio equity curve vs benchmark
├── lessons.jsonl              # EOD self-review lessons (self-learning)
├── monitor.json               # Live daemon state snapshot
├── steering/                  # File-drop IPC channel (daemon ↔ console)
├── surge/                     # EOD surge event store
├── early_session/             # Pre-market rapid-move events
├── data/cache/                # Intraday bar cache (TTL-bounded)
├── quality/                   # Quality metrics JSONL (F24)
├── config/
│   ├── config.py              # Pydantic Settings root
│   ├── settings.yaml          # Runtime configuration
│   ├── strategies.yaml        # Strategy registry and parameters
│   └── universe/              # Cached symbol universe snapshots
└── .env                       # API keys (gitignored)
```

## Key Configuration Knobs

| Setting | Default | Purpose |
|---|---|---|
| `app.mode` | `paper` | Trading mode: backtest / paper / live / agent |
| `broker.name` | `alpaca` | Broker: alpaca / kis |
| `broker.paper` | `true` | Use paper trading account |
| `data.provider` | `alpaca` | Data source: alpaca / yfinance / kis |
| `risk.max_position_pct` | `0.05` | Max 5% of equity per position |
| `risk.circuit_breaker_pct` | `0.02` | Halt new longs at 2% portfolio loss |
| `risk.shorting_enabled` | `false` | Master short switch (ships OFF — opt-in) |
| `risk.short_market_halt_threshold_pct` | `0.03` | Halt shorts if SPY up ≥ 3% |
| `risk.individual_stock_halt_pct` | `0.10` | Halt shorts on symbols up ≥ 10% |
| `trading.batch_interval_minutes` | `15` | Strategy evaluation cadence (batch mode) |
| `agent.turn_timeout` | `600` | LLM turn timeout in seconds |
| `agent.research_model` | `opus` | Model for research turns |
| `multi_agent.n_agents` | `3` | Number of sub-agents in research turn |
| `multi_agent.mode` | `sequential` | Sub-agent parallelism: sequential / parallel |
| `intraday.atr_k` | `1.5` | ATR multiplier for abnormal-move wake trigger |
| `surge.threshold_pct` | `7.0` | EOD surge detection threshold (7%) |
| `early_session.threshold_pct` | `5.0` | Early-session rapid-move threshold (5%) |
| `signals.ipo_horizon_days` | `5` | F78: surface IPOs within this many days |
| `signals.max_ipos` | `8` | F78: maximum IPOs in research brief |
| `signals.sources.ipo_provider` | `finnhub` | F78: IPO data source (`finnhub` or `none`) |

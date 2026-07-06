# Infrastructure Design

## Deployment Model

- **Platform**: Local workstation or any Linux server; no cloud-specific infrastructure (no CDK, Terraform, or CloudFormation)
- **Orchestration**: Manual — systemd --user unit via operator-console launcher, or bare `python main.py`
- **Runtime**: Python 3.11+ process (`autostockd` entry point or `python main.py`); TypeScript operator console (`autostock` launcher, Bun runtime)

## Stacks & Resources

### Python Daemon (`autostockd` / `main.py`)
- **Purpose**: Core trading daemon — agent orchestration, execution, data, risk, signals, monitoring
- **Key Resources**: Local filesystem (workspace/, data/, logs/, steering/), external broker APIs, LLM API
- **Defined In**: `main.py`, `src/`, `config/`

### Operator Console (`operator-console/`)
- **Purpose**: TypeScript TUI for human-in-the-loop supervision and steering
- **Key Resources**: `steering/` directory (shared file-drop with daemon), stdin/stdout TUI
- **Defined In**: `operator-console/src/`, `operator-console/launcher/`
- **Install**: `bun operator-console/launcher/install.ts` — creates `~/.local/bin/autostock` + optional systemd --user unit

### File-Drop Steering Channel (`steering/`)
- **Purpose**: IPC boundary between operator console and daemon; file-based for crash safety
- **Key Resources**: `steering/commands.jsonl`, `steering/events.jsonl`, `steering/snapshot.json`, `steering/codebase.json`
- **Defined In**: `src/agent/steering/channel.py`

### Runtime State (`workspace/`)
- **Purpose**: Agent's durable memory — journal, decisions, lessons, equity curve, trades, guidance
- **Key Resources**: `workspace/decisions.jsonl`, `workspace/lessons.jsonl`, `workspace/journal.md`, `workspace/guidance.md`, `workspace/equity_curve.jsonl`, `workspace/trades.jsonl`, `workspace/holdings/`, `workspace/interventions.jsonl`
- **Note**: gitignored — never committed to the repo

### Market Data Cache (`data/`)
- **Purpose**: Persistent market data and feature store
- **Key Resources**: `data/intraday/<SYM>.parquet` (per-symbol intraday features), `data/benchmark/` (baseline equity curves)
- **Note**: gitignored

## Environment Topology

| Environment | Account/Region | Purpose |
|---|---|---|
| Dev (local) | Alpaca paper account + claude CLI subscription | Development and paper trading |
| Paper (deployed) | Alpaca paper account, KIS paper account | Paper trading live session |
| Live (deployed, opt-in) | Alpaca live account, KIS live account | Real-money trading (`broker.paper: false`) |
| Benchmark sandbox | Alpaca Broker API sandbox accounts (one per baseline) | F70 shadow baseline comparison |

## CI/CD

- **Pipeline**: GitHub Actions
- **Config Location**: `.github/workflows/codekb-refresh.yml`
- **Tests**: pytest suite run via `Dockerfile.verify` + `scripts/verify.sh` / `docker-compose.verify.yml`
- **Pre-commit**: `.pre-commit-config.yaml` — gitleaks secret scan hook

### GitHub Actions Workflows

#### `codekb-refresh.yml`
- **Trigger**: Push to `main` (excluding `aidlc-docs/codekb/**` paths) + `workflow_dispatch`
- **Purpose**: Re-runs full Reverse Engineering and overwrites `aidlc-docs/codekb/`; single writer of CodeKB
- **Cooldown**: 4h minimum between refreshes; bypassed if >=3% of src lines changed or manual dispatch
- **Auth**: `CLAUDE_CODE_OAUTH_TOKEN` secret (Claude subscription token)
- **Bot identity**: `codekb-ci[bot]` — identified by git author + commit message for cooldown detection

## Configuration Precedence

```
CLI args > environment variables > .env > config/settings.yaml > code defaults
```

- Nested keys via `__` separator in env vars (e.g. `RISK__STOP_LOSS_PCT=0.03`)
- API keys: environment / `.env` only — never in `settings.yaml`
- Universe: `config/universe/{us,kr}_base.json` (snapshot fallback) + dynamic theme overlays
- Prompts: `config/prompts/trading_prompt_v1.txt` + version history in `config/prompts/prompt_history.json`
- `config/settings.yaml` — main app/broker/data/trading/risk/agent/signals/benchmark configuration
- `config/strategies.yaml` — active strategies list + per-strategy params

## Key External Dependencies

From `pyproject.toml`:
- `alpaca-py>=0.21.0` — Alpaca Trading + Broker + Data API SDK
- `python-kis==2.1.6` — KIS OpenAPI SDK (pinned; import: pykis)
- `anthropic>=0.18.0` — Claude API SDK
- `openai>=1.12.0` — OpenAI API SDK
- `pydantic>=2.5.0` + `pydantic-settings>=2.1.0` — models and settings
- `apscheduler>=3.10.0` — task scheduling (agent daily turns)
- `pyarrow>=14.0.0` — Parquet backend for intraday feature store
- `ta>=0.11.0` — technical analysis indicators
- `loguru>=0.7.0` — structured logging
- `hypothesis>=6.0` — property-based testing (dev)
- `pre-commit>=3.6` — secret scan hook (dev)

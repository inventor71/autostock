# Infrastructure Design

## Deployment Model
- **Platform**: Single-node process (developer machine / server); no cloud-native deployment.
- **Runtime**: Python >= 3.11 application run as a CLI/daemon (`main.py` dispatches modes).
- **Orchestration**: In-process APScheduler (`TradingScheduler`) — interval ticks + US-market cron
  for pre-market / intraday / EOD turns. No external orchestrator (no Kubernetes/ECS/Lambda).
- **Agent brain**: local `claude` CLI invoked as a subprocess; requires the CLI installed and authed
  on the host.

## Stacks & Resources
### Application process
- **Purpose**: Runs the selected trading mode (agent / realtime / batch / backtest).
- **Key Resources**: `workspace/` directory (journal + JSONL logs), `.env` for credentials.
- **Defined In**: `main.py`, `src/trading/modes/`

### State / storage
- **Purpose**: Durable agent memory and telemetry.
- **Key Resources**: file-based — `workspace/` markdown theses, `decisions.jsonl`, equity/trade/turn logs.
- **Note**: No database, queue service, or object store. Backups = filesystem.

## Environment Topology
| Environment | Account/Region | Purpose |
|---|---|---|
| paper | Alpaca paper / KIS 모의투자 | safe testing against real APIs (no real fills) |
| live | Alpaca live / KIS 실전 | real trading |
| backtest | local SimulatedBroker | offline replay, no external calls |
| test | isolated TEST account (`AUTOSTOCK_ENV_FILE`) | containerized verify harness |

## CI/CD
- **Pipeline**: GitHub Actions (`inventor71/autostock`).
- **CodeKB Refresh**: `.github/workflows/codekb-refresh.yml` — on every push to `main` (excluding
  `aidlc-docs/codekb/**`), re-runs Reverse Engineering via `anthropics/claude-code-action@v1` and
  commits the refreshed CodeKB back to `main`. Auth via `CLAUDE_CODE_OAUTH_TOKEN` secret;
  `GITHUB_TOKEN` needs write permission to push.
- **Verify harness**: containerized `worktree-setup.sh --docker-verify` →
  `docker compose ... run --rm verify {typecheck,unit,smoke}`, isolated to a TEST account.
- **Worktree gate**: `.claude/hooks/guard-main-edits.py` (PreToolUse) blocks app-code edits on the
  `main` checkout while any track is active; allowlist = `aidlc-docs/`, `.aidlc-rule-details/`,
  `.aidlc/`, `*.md`; override `AUTOSTOCK_ALLOW_MAIN_EDIT=1`.

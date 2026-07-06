# Integration Map

## External APIs

| API | Purpose | Connection | Auth | Criticality |
|---|---|---|---|---|
| Anthropic Claude | LLM portfolio-manager brain + operator console model | Headless `claude -p` CLI (subprocess) inside the daily session workspace | Local CLI subscription auth (`~/.claude/`), no `ANTHROPIC_API_KEY` needed for agent mode | High |
| Anthropic/OpenAI API | Pluggable LLM strategy signal source (classic path) | Direct HTTP API (anthropic / openai SDKs) | API key (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) | Medium |
| Alpaca Trading API | US equities order placement, positions, account (paper/live) | alpaca-py `TradingClient` | `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` (or `ALPACA_API_KEY`/`ALPACA_API_SECRET`) | High |
| Alpaca Broker API (account farm) | Sandbox multi-account isolation — per-instance sub-accounts | alpaca-py Broker API, `*_for_account` endpoints | Broker API key/secret | High (multi-instance deployments) |
| Alpaca Market Data | US historical/latest bars, quotes, trades, snapshots | `StockHistoricalDataClient` (lazy-init) | Same Alpaca credentials | High |
| KIS (Korea Investment Service) | Korean equities order placement + market data (paper/live) | Custom `KisRestClient` (raw REST, not pykis SDK); OAuth2 token (23h TTL, 1/min issuance cap) | appkey + appsecret + account number | Medium (regional) |
| yfinance | Market-data fallback (US), historical bars | `yfinance` Python package (public, unauthenticated) | None | Medium (fallback only) |
| yfinance News | News headlines + keyword-based sentiment scoring | `ticker.news` (yfinance) | None | Low |
| Finnhub | Earnings calendar, IPO calendar | REST `https://finnhub.io/api/v1/calendar/{earnings,ipo}` | `FINNHUB_API_KEY` (env, fail-honest if missing) | Medium |
| StockTwits | Retail sentiment (bullish/bearish tag streams) | REST `https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json` (unauthenticated, desktop User-Agent to avoid bot filter) | None | Low |
| SEC EDGAR | Disclosed institutional holdings (13F filings) | Public HTTP + CUSIP-to-ticker map | None | Low |
| Tailscale | Secure remote network for mobile operator-console access | `tailscale ip -4` CLI, Tailscale HTTPS certs | Tailscale device auth (external) | Medium (mobile path only) |

## Internal Process Integrations

| Channel | Producer | Consumer | Mechanism | Purpose |
|---|---|---|---|---|
| `steering/commands.jsonl` | operator-console (human) | Python daemon (SteeringChannel) | Append-only file, torn-safe read, HMAC token validated | Human steering commands (buy/sell/pause/halt/approve/...) |
| `steering/events.jsonl` | Python daemon | operator-console | Append-only file, tailed (~1.5s poll) | Command outcomes, fills, pending approvals, lifecycle events |
| `steering/snapshot.json` | Python daemon | operator-console, mobile dashboard, F94 account-truth reader | Atomic write (temp + `os.replace`), single-writer | Live account/portfolio/health/pending-approval view |
| `steering/monitor.json` | Python daemon | operator-console | Same atomic pattern | Deep monitoring (turn cost, recent decisions, log tail) |
| `workspace/positions/<SYMBOL>.md` | Agent (claude CLI Write tool, non-atomic) | operator-console (stat-stable read, F76) | Plain file; reader retries on size/mtime change (max 5) | Per-symbol investment thesis |
| `workspace/triggers/<id>/*` | Agent (create) / TriggerEvaluator (state) | Intraday WakeDetector | JSON files (spec.json, predicate.py, state.json) | F88 self-authored long-horizon macro/news wake predicates |
| MCP stdio server (`mcp-server.ts`) | operator-console LLM (opencode) | Steering/Alpaca-read tool handlers | MCP tool calls, auto-gated by opencode permission engine (`ask`/`allow`) | Structured order placement + read-only Alpaca/daemon introspection |
| `/autostock/webauthn/*`, `/autostock/dashboard` HTTP routes | operator-console HTTP listener | Mobile PWA / phone browser | Effect-based HTTP routes mounted before the SPA catch-all (F93 fix) | Remote WebAuthn passkey verification + read-only dashboard JSON |

## Databases & Data Stores

| Store | Type | Purpose | Access Pattern |
|---|---|---|---|
| `workspace/decisions.jsonl` | JSONL (file) | Agent decision journal (BUY/SELL/HOLD/...) | Append-only write (agent), torn-safe complete-line read (executor) |
| `workspace/.executor_state.json` | JSON (file) | Idempotent execution cursor (line count + terminal indices) | Read-modify-atomic-write per executor pass |
| `workspace/lessons.jsonl` | JSONL (file) | Structured self-learning lessons (category, signal_used, outcome, regime, sector) | Append-only |
| `workspace/equity.jsonl` | JSONL (file) | EOD equity/P&L snapshots | Append-only |
| `workspace/execution_outcomes.jsonl` | JSONL (file) | All decision outcomes (executed/skipped/error) | Append-only |
| `workspace/positions/<SYMBOL>.md` | Markdown (file) | Per-symbol thesis | Non-atomic write (agent), stat-stable read (console) |
| `workspace/surge/history.jsonl`, `analyses.jsonl` | JSONL (file) | EOD surge/dive detections + agent root-cause analysis | Append-only |
| `workspace/sentiment/{ET-date}.jsonl` | JSONL (file) | Hourly StockTwits sweep history | Append-only (daemon sweep writer) |
| `workspace/holdings/{source_id}/` | JSON (file) | Cached disclosed-holdings snapshots (13F) | Daemon refresher writes (HTTP); research turn reads cache only |
| `config/universe/*.json` (snapshot) | JSON (file) | Cached tradeable-symbol universe (1-day TTL) | Atomic write, fail-closed fallback to last good snapshot |
| `workspace/kis_oco_groups.json` | JSON (file) | KIS OCO emulation bookkeeping (resting limit + polled/exchange stop) | Read-modify-write |
| SQLite/Parquet intraday feature store (`src/data`/`intraday_collection`) | Parquet | Auto-collected intraday bars for offline ML feature engineering | Append batch writes |

## Message Queues & Events

autostock has no external message broker (no SQS/SNS/Kafka). All async coordination is via
the file-drop JSONL/JSON convention above, plus in-process APScheduler jobs:

| Queue/Topic (logical) | Type | Producer | Consumer | Purpose |
|---|---|---|---|---|
| Intraday wake events | In-process (5s scheduler tick, coalesced) | `WakeDetector` (cache-only reads) | `AgentTradingLoop` | Fires one coalesced agent turn per buffered window (new_fill, abnormal_move, watch_trigger, protective_reassess, agent_trigger) |
| Off-hours human trades | JSONL file (`pending_human_trades.jsonl`) | Steering runtime (market closed) | Scheduler at next open | Defers human trade commands issued while market is closed |

# Integration Map

## External APIs
| API | Purpose | Connection | Auth | Criticality |
|---|---|---|---|---|
| Anthropic Claude (CLI) | LLM portfolio-manager brain (default agent/research path) + operator console model | Headless `claude -p` CLI (subprocess), `--output-format json`, tools denied, neutral tmp cwd | Local CLI subscription auth (`~/.claude/`), no `ANTHROPIC_API_KEY` needed | High |
| Anthropic Claude (API) | Pluggable direct-API LLM backend (`ClaudeClient`) — classic single-shot path and eval harness | Direct HTTPS via `anthropic` SDK (`messages.create`); adaptive thinking + `output_config.effort` for modern model families (`claude-sonnet-5`, `claude-opus-5`, `claude-haiku-5`, `claude-fable-*`) | `ANTHROPIC_API_KEY` | Medium |
| OpenAI API (Astra / gpt-6 family) | Pluggable LLM agent/research backend (`OpenAIClient`) — alternative to Claude for trading turns | Direct HTTPS via `openai` SDK, Responses API (`responses.create`), reasoning `effort` for `gpt-5`/`gpt-6`/`o1`/`o3`/`o4` model families, `store=False` | `OPENAI_API_KEY` | Medium |
| Alpaca Trading API | US equities order placement, positions, account (paper/live) | alpaca-py `TradingClient` | `APCA_API_KEY_ID`/`APCA_API_SECRET_KEY` (or `ALPACA_API_KEY`/`ALPACA_API_SECRET`) | High |
| Alpaca Broker API (account farm) | Sandbox multi-account isolation — per-instance sub-accounts | alpaca-py Broker API (`BrokerClient`), `*_for_account` endpoints, order envelopes, trade-activity pagination | Broker API key/secret | High (multi-instance deployments) |
| Alpaca Market Data | US historical/latest bars, quotes, trades, snapshots | `StockHistoricalDataClient` (lazy-init) | Same Alpaca credentials | High |
| KIS (Korea Investment Service) | Korean equities order placement + market data (paper/live) | Custom `KisRestClient` (raw REST, not pykis SDK); OAuth2 token (23h TTL, 1/min issuance cap); 모의투자 vs 실전 capability differences (e.g. no stop-limit in paper) | appkey + appsecret + account number | Medium (regional) |
| yfinance | Market-data fallback (US), historical bars | `yfinance` Python package (public, unauthenticated) | None | Medium (fallback only) |
| yfinance News | News headlines + keyword-based sentiment scoring | `ticker.news` (yfinance) | None | Low |
| Finnhub | Earnings calendar, IPO calendar | REST `https://finnhub.io/api/v1/calendar/{earnings,ipo}` (one call per date range) | `FINNHUB_API_KEY` (env, fail-honest if missing) | Medium |
| StockTwits | Retail sentiment (bullish/bearish self-declared tag streams) | REST `https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json` (unauthenticated, desktop User-Agent to dodge bot filter); `RateLimited` raised on 403/429 | None | Low |
| SEC EDGAR | Disclosed institutional holdings (13F filings) | Public HTTP + CUSIP-to-ticker map | None | Low |
| Tailscale | Secure remote network for mobile operator-console access | `tailscale ip -4` CLI, Tailscale HTTPS certs | Tailscale device auth (external) | Medium (mobile path only) |
| Slack (Incoming Webhook) | Trading alert notifications | HTTPS POST to Slack webhook URL (`urlopen`, 5s timeout) | Webhook URL (secret-by-possession) | Low |
| Telegram Bot API | Trading alert notifications | HTTPS GET `https://api.telegram.org/bot{token}/sendMessage` (`urlopen`, 5s timeout) | Bot token + chat ID | Low |

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
| Intraday Parquet feature store (`src/data/intraday`) | Parquet | Auto-collected intraday bars for offline ML feature engineering | Append batch writes |
| `research-comparisons/<experiment>/` (`summary.md`, `summary.csv`, per-run artifacts) | JSON/CSV/Markdown (gitignored files) | Model/profile comparison results from `src.evals.compare_research` (single/sequential/parallel research modes, Fable/Astra/Opus profiles) | Append-only per experiment; indexed by `research-comparisons/README.md` |
| Eval scenario/outcome fixtures (`src.evals.scenario`, `src.evals.returns`) | JSON (file) | Frozen decision scenarios + synthetic/historical/forward `OutcomePath` future-bar tapes for post-decision return grading | Write-once per scenario; read-only replay via `SimulatedBroker` subclass |

## Message Queues & Events
autostock has no external message broker (no SQS/SNS/Kafka). All async coordination is via file-drop JSONL/JSON channels plus in-process APScheduler jobs.

| Queue/Topic | Type | Producer | Consumer | Purpose |
|---|---|---|---|---|
| `steering/commands.jsonl` | File-drop (append-only JSONL, torn-safe read, HMAC-validated) | operator-console (human) | Python daemon (SteeringChannel) | Human steering commands (buy/sell/pause/halt/approve/...) |
| `steering/events.jsonl` | File-drop (append-only JSONL, tailed ~1.5s poll) | Python daemon | operator-console | Command outcomes, fills, pending approvals, lifecycle events |
| `steering/snapshot.json` | File-drop (atomic write: temp + `os.replace`, single-writer) | Python daemon | operator-console, mobile dashboard, F94 account-truth reader | Live account/portfolio/health/pending-approval view |
| `steering/monitor.json` | File-drop (same atomic pattern) | Python daemon | operator-console | Deep monitoring (turn cost, recent decisions, log tail) |
| `steering/quotes.json` | File-drop (same atomic pattern) | Python daemon (`QuoteBook`) | operator-console `SymbolOverlay` | Warm quote feed for symbol click-through (F95) |
| `workspace/positions/<SYMBOL>.md` | File-drop (non-atomic write, stat-stable retry read, max 5) | Agent (claude CLI Write tool) | operator-console (F76) | Per-symbol investment thesis |
| `workspace/triggers/<id>/*` | File-drop (JSON files: spec.json, predicate.py, state.json) | Agent (create) / TriggerEvaluator (state) | Intraday WakeDetector | F88 self-authored long-horizon macro/news wake predicates |
| Intraday wake events | In-process (5s scheduler tick, coalesced) | `WakeDetector` (cache-only reads) | `AgentTradingLoop` | Fires one coalesced agent turn per buffered window (new_fill, abnormal_move, watch_trigger, protective_reassess, agent_trigger) |
| `pending_human_trades.jsonl` | File-drop (JSONL) | Steering runtime (market closed) | Scheduler at next open | Defers off-hours human trade commands until market open |
| MCP stdio server (`mcp-server.ts`) | IPC (stdio, MCP tool calls, opencode permission-gated `ask`/`allow`) | operator-console LLM (opencode) | Steering/Alpaca-read tool handlers | Structured order placement + read-only Alpaca/daemon introspection |
| `/autostock/webauthn/*`, `/autostock/dashboard` HTTP routes | HTTP (Effect-based routes mounted before SPA catch-all, F93 fix) | operator-console HTTP listener | Mobile PWA / phone browser | Remote WebAuthn passkey verification + read-only dashboard JSON |

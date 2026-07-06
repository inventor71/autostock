# Integration Map

## External APIs

| API | Purpose | Connection | Auth | Criticality |
|---|---|---|---|---|
| Alpaca Trading API | US equities paper/live trading (orders, positions, fills, news) | REST + WebSocket | `ALPACA_API_KEY`, `ALPACA_API_SECRET` | high |
| Alpaca Broker API | Multi-account farm (sandbox accounts for benchmark baselines) | REST | `BROKER_API_KEY`, `BROKER_API_SECRET`, `BROKER_ACCOUNT_ID` | medium |
| KIS (Korea Investment & Securities) | Korean equities paper trading and market data | REST (python-kis SDK) | `KIS_PAPER_API_KEY`, `KIS_PAPER_API_SECRET`, `KIS_PAPER_ACCOUNT` | medium |
| Anthropic Claude API | LLM portfolio manager brain (research + decision turns) | HTTP (anthropic SDK) or claude CLI headless | `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` | high (agent mode) |
| OpenAI API | Alternative LLM backend | HTTP (openai SDK) | `OPENAI_API_KEY` | low (optional) |
| yfinance | Free market data fallback (OHLCV bars, fundamentals) | REST (yfinance library) | None | medium |
| Finnhub | Earnings calendar and IPO calendar | REST | `FINNHUB_API_KEY` (env) | medium |
| StockTwits | Retail sentiment (hourly author self-labels sweep) | REST | None (unauthenticated, rate-limited ~200/hr) | low |
| SEC EDGAR | Institutional 13F disclosed holdings | HTTPS (fair-access UA required) | None (identifying User-Agent required) | low |
| Alpaca News | Market news headlines for research prompts | REST (alpaca-py) | Same Alpaca keys | medium |
| Slack | Operational alerts | Webhook POST | `SLACK_WEBHOOK` (env) | low |
| Telegram | Operational alerts | Bot API | `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` (env) | low |

## Databases & Data Stores

| Store | Type | Purpose | Access Pattern |
|---|---|---|---|
| `workspace/decisions.jsonl` | JSONL file (append-only) | Machine-executable decisions written by agent, read by executor | append-write (agent), sequential-read with cursor (executor) |
| `workspace/lessons.jsonl` | JSONL file (append-only) | Outcome-attributed lessons from EOD review | append-write (review), sequential-read (recall) |
| `workspace/equity_curve.jsonl` | JSONL file (append-only) | Daily equity snapshots for performance tracking | append-write (executor), read (EOD review, quality) |
| `workspace/theses.md` | Markdown file | Narrative investment theses per symbol | write (agent), read (agent research prompts) |
| `workspace/journal.md` | Markdown file | Daily trading journal narrative | write (agent) |
| `workspace/guidance.md` | Markdown file | Agent's self-rewritten guidance prompt (constitution-bounded) | write (self_rewrite), read (orchestrator) |
| `workspace/trades.jsonl` | JSONL file (append-only) | FIFO-matched closed round-trips | append-write (executor), read (quality metrics) |
| `workspace/interventions.jsonl` | JSONL file (append-only) | Audit log of every human steering action and its outcome | append-write (steering commands), read (audit) |
| `workspace/holdings/` | JSON files (per-source) | Cached institutional 13F holdings snapshots | write (background refresher), read (universe overlay, signal brief) |
| `data/benchmark/` | JSON files | Benchmark baseline equity curves and trade ledgers | write (BenchmarkRunner), read (quality aggregate) |
| `data/intraday/<SYM>.parquet` | Parquet files | Per-symbol intraday session features (auto-collected) | append-write (F82 collector), read (intraday analysis) |
| `steering/commands.jsonl` | JSONL file (file-drop) | Operator to daemon steering commands | append-write (operator console), sequential-read (SteeringChannel) |
| `steering/events.jsonl` | JSONL file (file-drop) | Daemon to operator outcomes/fills/events | append-write (daemon), tail-read (operator console) |
| `steering/snapshot.json` | JSON file (atomic write) | Live daemon read view (positions, orders, fills) | atomic-write (daemon), read (operator console) |
| `config/prompts/trading_prompt_v1.txt` | Text file | Base LLM trading prompt | read (PromptManager) |
| `config/prompts/prompt_history.json` | JSON file | Versioned prompt performance history | read-write (PromptManager, auto-improver) |

## Message Queues & Events

| Queue/Topic | Type | Producer | Consumer | Purpose |
|---|---|---|---|---|
| `steering/commands.jsonl` | File-drop JSONL | Operator console | SteeringChannel (daemon) | Human steering commands with HMAC auth |
| `steering/events.jsonl` | File-drop JSONL | SteeringChannel (daemon) | Operator console | Outcome events, fills, pending orders, agent status |
| `workspace/decisions.jsonl` | File-based | AgentTradingLoop | DecisionExecutor | Machine-executable decisions from agent to executor |
| Alpaca WebSocket | WebSocket | Alpaca (exchange) | RealtimeTradingMode | Real-time trade bar stream for realtime mode |

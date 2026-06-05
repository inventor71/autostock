# Integration Map

## External APIs
| API | Purpose | Connection | Auth | Criticality |
|---|---|---|---|---|
| Alpaca (alpaca-py) | US market data + trading (paper/live) | REST/WebSocket | API key/secret (env) | high |
| KIS OpenAPI (python-kis 2.1.6, import `pykis`) | Korean-equity broker/data | REST | KIS app key/secret (env, paper+live) | high |
| yfinance | Backup/secondary market data + news | HTTP scrape | none | medium |
| Anthropic API | LLM strategy (`src/strategy/llm/`) | REST | API key (env) | medium |
| OpenAI API | Alternate LLM strategy | REST | API key (env) | low |
| local `claude` CLI | Agent brain — agentic portfolio manager (`AgentSession`) | subprocess (`claude -p`) | local CLI auth | high (agent mode) |
| Finnhub | Earnings calendar signal (`src/signals/sources/finnhub_earnings.py`) | REST | API key (env) | medium |

## Databases & Data Stores
| Store | Type | Purpose | Access Pattern |
|---|---|---|---|
| `workspace/` journal | file (markdown + JSONL) | Agent durable memory: theses + append-only `decisions.jsonl` | read-write |
| telemetry logs | JSONL files | per-turn cost, daily equity, closed trades, lessons | append/read |
| (none) | — | No relational/NoSQL database; all persistence is file-based | — |

## Message Queues & Events
| Queue/Topic | Type | Producer | Consumer | Purpose |
|---|---|---|---|---|
| `decisions.jsonl` | append-only file (cursor-based) | AgentTradingLoop (brain) | DecisionExecutor (body) | hand-off of trade decisions; idempotent via cursor file |
| APScheduler jobs | in-process scheduler | `TradingScheduler` | trading modes | interval ticks + US-market cron turns (pre-market/intraday/EOD) |

## Notes
- **KIS specifics**: pykis 2.1.6 has no `stop` param; 모의투자(paper) does not support stop-limit
  (`ORD_DVSN=22`), live-only; env keys `KIS_PAPER_API_*`. (See project memory `kis-api-facts`.)
- **Auth model**: all external credentials come from environment variables / `.env`; no secrets in repo.

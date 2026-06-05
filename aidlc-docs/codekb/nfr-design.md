# NFR Design

> NFR patterns observable in the codebase at HEAD `3572f30` (2026-06-05).

## Resilience
| Pattern | Implementation | Location |
|---|---|---|
| Idempotent journal consumption | Cursor file tracks last-consumed decision; safe across restarts | `src/agent/executor.py` |
| Exchange-resting protection | BRACKET/OCO legs rest at the broker (not only polled) | `src/risk/manager.py`, `src/agent/executor.py` |
| Circuit breaker / expiry / pool checks | Guards before routing agent decisions | `src/agent/executor.py` |
| Fail-honest collectors | Signals/data collectors surface failures rather than fabricating | `src/signals/`, `src/data/providers/` |
| Polled stop/take-profit (legacy mode) | Engine polls exits when not in bracket mode | `src/trading/engine.py` |
| Event-driven intraday wakes | Wake detector (5s, cache-only) fires on fills/abnormal moves/watch triggers without blocking the scheduler thread | `src/agent/intraday/wake.py`, `src/agent/intraday/abnormal.py` |
| Single turn lock | All LLM turns serialised by a single `turn_lock`; human reconcile waits at most one wake turn | `src/agent/steering/turns.py` |

## Scalability
| Pattern | Implementation | Location |
|---|---|---|
| Per-symbol cycle | `run_cycle()` iterates the universe; `run_cycle_for_symbol()` for realtime | `src/trading/engine.py` |
| Market-time scheduling | APScheduler interval + US-market cron via `TradingScheduler` | `src/trading/` |
| File-based state (no DB) | `workspace/` journal + JSONL logs; low-ops, single-node | `src/agent/` |

## Security
| Pattern | Implementation | Location |
|---|---|---|
| Secrets via environment | All broker/LLM credentials from env / `.env`; none in repo | config / brokers |
| Paper/live separation | Distinct paper vs live API keys (Alpaca, KIS `KIS_PAPER_API_*`) | `src/execution/brokers/` |

## Observability
| Pattern | Implementation | Location |
|---|---|---|
| Per-turn telemetry | turn cost/log | `src/agent/turn_log.py` |
| Equity vs benchmark | daily equity ledger | `src/agent/equity_log.py` |
| Closed round-trips | trade ledger | `src/agent/trades_log.py` |
| EOD self-review → lessons | review + efficacy/lessons | `src/agent/review.py` |
| Structured logging | loguru | project-wide |
| Health monitoring | health checks | `src/monitoring/health/` |

## Known Structural Debt
- **S-2**: `RiskManager` is dual-mode toggled by a boolean (`use_bracket_orders`: legacy market-order + polled exits vs resting BRACKET/OCO). The two modes diverge in behavior.
- **S-3**: Some `src/` modules reach into the config singleton directly (layer violation vs injecting through `main.py`).
- Short-selling is implemented (F60) but shipped OFF by default (`shorting_enabled: false` in settings.yaml) — opt-in.
- LLM auto-improvement loop does not automatically re-backtest with the new prompt (manual re-run needed).

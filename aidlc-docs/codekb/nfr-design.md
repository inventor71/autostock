# NFR Design

> NFR patterns observable in the codebase at HEAD `58ca6a7`. Some structural findings from the M1
> reverse-engineering snapshot (2026-05-28) may have been addressed by later tracks.

## Resilience
| Pattern | Implementation | Location |
|---|---|---|
| Idempotent journal consumption | Cursor file tracks last-consumed decision; safe across restarts | `src/agent/executor.py` |
| Exchange-resting protection | BRACKET/OCO legs rest at the broker (not only polled) | `src/risk/manager.py`, `src/agent/executor.py` |
| Circuit breaker / expiry / pool checks | Guards before routing agent decisions | `src/agent/executor.py` |
| Fail-honest collectors | Signals/data collectors surface failures rather than fabricating | `src/signals/`, `src/data/providers/` |
| Polled stop/take-profit (legacy mode) | Engine polls exits when not in bracket mode | `src/trading/engine.py` |

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

## Known Structural Debt (M1 snapshot — verify current state)
- **S-2**: `RiskManager` is dual-mode toggled by a boolean (bracket vs legacy).
- **S-3**: Some `src/` modules reach into the config singleton directly (layering leak).
- **S-4**: Broker abstraction had duck-typing leaks around `BaseBroker`.
- **H-1**: Short positions were half-modeled.
(Several B-series backtest bugs were fixed in commit `9384b3c`.)

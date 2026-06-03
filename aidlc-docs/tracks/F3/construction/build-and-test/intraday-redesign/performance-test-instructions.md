# Performance / Non-Functional Test Notes — Unit `intraday-redesign` (F3)

> Formal load/stress/scalability testing is **N/A**: F3 is a single-operator local daemon with no request load, no SLA, and the dominant latency (LLM turn) is external and unbounded by design. The relevant non-functional concerns are **responsiveness and concurrency safety**, verified below.

## NF-1 — Wake detector must not block the scheduler thread (critic#3)
- **Concern**: the 5s `agent_wake` job shares APScheduler's default pool; a synchronous market-data fetch exceeding 5s would make `coalesce` silently drop ticks.
- **Design guard**: `WakeDetector.detect_wakes` reads **cached data only** (`last_snapshot` + `BarCache` with 60s bars / 3s price TTL); no synchronous quote/bars fetch on the scheduler thread. `_JOB_DEFAULTS` sets `misfire_grace_time=30`.
- **Check**: covered by `test_intraday_wake.py` (detector uses injected caches, no provider call per tick) and `test_intraday_bars.py` (TTL routing serves from cache within TTL).
- **Live observation (optional)**: under a volatile session, confirm the wake job stays under its interval (no repeated `misfire`/`coalesce` warnings in the daemon log).

## NF-2 — Single-worker broker invariant (NFR-2)
- All broker access (incl. `get_fills`) runs on the **one CommandBus worker** via `publish_snapshot._build`; detectors/brief read `last_snapshot` only.
- **Known bound (accepted)**: during an emergency lane / long executor batch, snapshot+fills publish queues behind it, so new-fill awareness can lag by the bus backlog. Safe because OCO protection is exchange-mechanical; only the *judgement* wake is delayed.
- **Check**: `test_intraday_snapshot.py` (fills collected on the worker); reasoning recorded in nfr-design §P2.

## NF-3 — Turn serialization & human responsiveness (NFR-1, critic#2)
- All LLM turns go through one `turn_lock`. `ReconcileWorker` uses **per-kind timers**, so a wake burst cannot cancel/starve the human reconcile timer.
- **Inherent bound (not removed)**: a human reconcile arriving while a wake turn is in-flight waits for that one turn (single-session model). Wake turns carry a turn-level timeout (default 120s, `intraday.wake.timeout`) to cap the hold.
- **Check**: `test_intraday_wake.py::test_per_kind_timers_do_not_starve_human`, `::test_wake_timeout_passed_through`; `test_intraday_integration.py` (skip-if-busy).

## NF-4 — Fault isolation (NFR-4)
- Wake detection, brief assembly, news polling, watch evaluation, and `get_fills` are all best-effort (exceptions logged, never raised into the scheduler/daemon).
- **Check**: failure-path tests in `test_intraday_news.py`, `test_intraday_bars.py`, `test_intraday_fills.py`.

## NF-5 — Cost / token (informational)
- Goal of F3 is correctness + responsiveness, NOT cost reduction (per requirements §3). The structured brief removes redundant tool calls (quote×N re-pulls) per scheduled turn, which incidentally lowers tokens, but no token SLA is asserted. Per-turn cost is captured in `workspace/turns.jsonl` (`turn_log`) and can be compared pre/post live.

## Out of scope (N/A)
- Load/stress/throughput, horizontal scalability, multi-tenant — single local daemon.
- Backtest performance — the agentic path is not backtested (web/non-determinism), per [[llm-trader-redesign]] #7.

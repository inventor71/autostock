# Stage 3 — Redesign decisions: ET helpers

**Track**: R6 · **Date**: 2026-06-07

## Module
`src/core/markettime.py` (core layer, depends on nothing):
```python
ET = ZoneInfo("America/New_York")   # canonical; US/Eastern is its alias
def et_now()   -> datetime: return datetime.now(ET)
def et_today() -> date:     return et_now().date()
```

## Decision 1 — `today_et()` shim vs rename → **rename to `et_today()`, no shim**
The guide offered "keep a re-export shim" or "update importers and remove". Chosen: **remove
`today_et`, migrate all callers to `et_today` from core.** Rationale: the project's refactor norm is
*native* (read as if always that way; no migration-shim residue), and the smell being fixed is the
**downward import** (`watch_store` → `steering/state`). Pointing every caller at `core` eliminates the
smell outright; a shim would preserve it. Callers: `steering/state.py` (~13 internal), `steering/
channel.py` (3), `intraday/watch_store.py` (3). Cost is mechanical; no behavior change.

## Decision 2 — `compute_et_date` stays in `turn_log`, only swaps the constant
`compute_et_date(ts)` is richer than `et_today()` (parses arbitrary `None`/str/datetime, naive→local
→ET, bad-string fallback) and is pinned by `tests/test_timeline_f25.py`. **Not** folded into
`et_today()`. It just imports the shared `ET` instead of its private `_MARKET_TZ`. (Moving the whole
function to core was considered and rejected: it's a logging concern with 3 in-package callers — out
of scope, no dedup win.)

## Decision 3 — KST / scheduler left separate
`kis_broker._KST` (Korea) and `scheduler.timezone` (generalized string param, broker-overridable)
are not ET-constant duplicates. Untouched. A future `market_tz(broker)` generalization is noted but
out of scope for R6.

## Migration order (Stage 4)
1. `core/markettime.py` (done) + `tests/test_markettime.py` (done, green).
2. Swap constants: `core/trades.py`, `early_session/monitor.py`, `agent/session.py`,
   `agent/turn_log.py`, `agent/steering/runtime.py`.
3. Move helper: define nothing new in `state.py`; `from src.core.markettime import ET, et_today`;
   rename internal `today_et()` calls → `et_today()`; remove the old def.
4. Update importers `steering/channel.py`, `intraday/watch_store.py` → import `et_today` from core.
5. Update monkeypatch targets in `test_steering_state.py`, `test_intraday_watch.py`.
6. Full suite green → Build & Test.

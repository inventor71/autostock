# Pick-up guide — R6: ET (market timezone) helpers

**Status**: backlog (not started). Survey base `ec2875c` (2026-06-06).

## Why
The market timezone is declared independently in ~6 modules, under **two spellings of the same
zone**. `US/Eastern` is a tz-database backward-compat alias for `America/New_York` — identical
offset and DST rules — so today's behavior is consistent *by luck of them being aliases*, not by
design. One shared constant removes the drift risk and the awkward import direction.

## Evidence (call sites at survey time)
Refresh: `grep -rnE 'ZoneInfo\("(US/Eastern|America/New_York)"\)|today_et|compute_et_date' src --include='*.py'`

- `ZoneInfo("US/Eastern")`: `src/agent/session.py:39`, `src/agent/steering/state.py:31`,
  `src/trading/scheduler.py` (param default, ×3)
- `ZoneInfo("America/New_York")`: `src/early_session/monitor.py:30`, `src/core/trades.py:14`,
  `src/agent/turn_log.py:21` (`_MARKET_TZ`), `src/agent/steering/runtime.py:639` (`_MARKET_TZ`)
- `today_et()` defined in `src/agent/steering/state.py:34`; imported by
  `src/agent/intraday/watch_store.py:21` (downward dep into a high-level module — smell)
- `src/agent/turn_log.py:62` has its own `compute_et_date()`

**Leave separate**: `src/execution/brokers/kis_broker.py:36` `_KST = ZoneInfo("Asia/Seoul")` (Korea,
not the US market tz). Note for a possible future `market_tz(broker)` generalization — out of scope.

## Proposed shape (decide in Stage 3)
```python
# src/core/markettime.py  (core depends on nothing — correct layer)
from datetime import date, datetime
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")        # canonical spelling
def et_now() -> datetime: return datetime.now(ET)
def et_today() -> date:   return et_now().date()
```
Then:
- replace each local `_ET`/`_MARKET_TZ` with `from src.core.markettime import ET`
- `today_et()` → re-export from `core` (keep `src/agent/steering/state.py::today_et` as a thin
  re-export shim, OR update its 1 importer — `watch_store.py` — and remove it; Stage 3 decision)
- fold `turn_log.compute_et_date()` onto `et_today()` (verify it's the same thing first)

## Tiering
**Pure T1.** The one thing to *prove* (Stage 1 characterization): `US/Eastern` and
`America/New_York` resolve to identical offsets across a DST boundary — a 2-line test
(`assert datetime(2026,1,1,tzinfo=ZoneInfo("US/Eastern")).utcoffset() == …America/New_York…`
and a July date). Once proven, the spelling normalization is behavior-preserving.

> ⚠ If any site relied on a *different* zone by accident, that surfaces here as a failing
> characterization test → escalate to T3. Not expected, but check.

## Test net
`tests/test_logs.py`, `tests/test_timeline_f25.py`, `tests/test_steering_state.py`,
`tests/test_early_session.py`. Add `tests/test_markettime.py` (alias-equivalence + et_today/now).

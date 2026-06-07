# Stage 1 — Baseline + characterization: ET (market timezone) helpers

**Track**: R6 · **Date**: 2026-06-07 · **Base**: 5e5c2a9 (post R3/R4/R5)

## Current state (refreshed survey)

### Duplicated ET constant — 7 declarations, 2 spellings of the *same* zone
| Site | Spelling | Name |
|------|----------|------|
| `src/agent/steering/state.py:31` | `US/Eastern` | `_ET` (used by `today_et()`) |
| `src/agent/session.py:39` | `US/Eastern` | `_ET` (session_date roll) |
| `src/core/trades.py:14` | `America/New_York` | `_ET` |
| `src/early_session/monitor.py:30` | `America/New_York` | `_ET` |
| `src/agent/turn_log.py:22` | `America/New_York` | `_MARKET_TZ` |
| `src/agent/steering/runtime.py:639` | `America/New_York` | `_MARKET_TZ` |
| `scripts/agent_trace.py:33` | `US/Eastern` | `_ET` (found by /code-review — survey grepped `src/` only) |

> The 7th site (`scripts/agent_trace.py`) was missed by the initial survey (it greps `src/`). A
> high-effort `/code-review` caught it: leaving it would falsify the "single source of truth" claim.
> Folded in — the script now does `sys.path.insert(0, repo_root)` then imports `ET`/`et_today` from
> core (mirroring its siblings `scripts/status.py`, `scripts/health.py`).

`US/Eastern` is a tz-database backward-compat **alias** of `America/New_York` (identical offset +
DST rules), so today's behavior is consistent *by alias luck*, not by design — the drift risk this
track removes.

### Helper duplication / smell
- `today_et() -> date` defined in `src/agent/steering/state.py:34` (`datetime.now(_ET).date()`),
  imported **downward** by `src/agent/intraday/watch_store.py:21` (high-level module imported by a
  lower one — the import-direction smell). Also imported by `src/agent/steering/channel.py:27`
  (sibling, fine) and used ~13× internally in `state.py`.
- `compute_et_date(ts) -> str` in `src/agent/turn_log.py:34` — **richer** than `today_et()`:
  accepts `None`/ISO-string/`datetime`, interprets naive values in local tz, converts to ET, with a
  bad-string fallback. **NOT foldable into `et_today()`** (which only answers "now"). Keep it; only
  swap its `_MARKET_TZ` for the shared `ET`. `compute_et_date(None)` ≡ `et_today().isoformat()`.

### Out of scope (documented exclusions)
- `src/trading/scheduler.py` `timezone: str = "US/Eastern"` (×3) — a **string** cron-tz param passed
  to APScheduler, intentionally generalized + broker-overridable (`Asia/Seoul` for KR). Not a
  hardcoded ET-constant dup; normalizing only changes log text. Leave as-is.
- `src/execution/brokers/kis_broker.py` `_KST = ZoneInfo("Asia/Seoul")` — Korea tz, not US market.
  (Future `market_tz(broker)` generalization — out of scope.)

## Characterization (behavior to preserve)
1. **Alias equivalence (the T1 proof)**: `ZoneInfo("US/Eastern")` and `ZoneInfo("America/New_York")`
   resolve to identical UTC offset on both a winter (EST) and a summer (EDT) date. Once proven,
   spelling normalization to `America/New_York` is behavior-preserving.
2. **`et_today()`** == current ET calendar date == old `today_et()`.
3. **`compute_et_date`** existing behavior pinned by `tests/test_timeline_f25.py` (naive→local→ET,
   tz-aware passthrough, bad-string fallback) — must stay byte-identical after the `_MARKET_TZ`→`ET`
   swap.

### Existing test net (relied upon)
- `tests/test_timeline_f25.py` — `compute_et_date` cases.
- `tests/test_steering_state.py` — monkeypatches `state_mod.today_et` (3×).
- `tests/test_intraday_watch.py` — monkeypatches `ws_mod.today_et`.
- `tests/test_logs.py`, `tests/test_early_session.py`, `tests/test_sidebar_upgrade.py`.
- **New**: `tests/test_markettime.py` — alias equivalence + `et_now`/`et_today`.

> Monkeypatch targets (`<module>.today_et`) move when callers switch to `et_today` — Stage 4 updates
> those 3 test files accordingly (the rename, not the behavior, changes).

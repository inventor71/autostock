# Stage 2 — Tier ledger: ET helpers

**Track**: R6 · **Date**: 2026-06-07 · Tiers per `ai-dlc-refactor` (T1 mechanical / T2 local-logic /
T3 behavior-risk → human gate).

| # | Change | Tier | Rationale |
|---|--------|------|-----------|
| 1 | New `src/core/markettime.py` (`ET`, `et_now`, `et_today`) | T1 | Additive; no caller yet. |
| 2 | Replace 6 local `_ET`/`_MARKET_TZ = ZoneInfo(...)` with `from src.core.markettime import ET` | T1 | Alias-equivalence **proven** (`tests/test_markettime.py`) → spelling normalization behavior-preserving. |
| 3 | `today_et()` → `et_today()`: move impl to core, migrate callers (`steering/state.py`, `steering/channel.py`, `intraday/watch_store.py`), remove old def | T1 | Pure rename + import redirect; same return (`date`). Removes the downward-import smell. |
| 4 | `turn_log.compute_et_date` / `runtime` use shared `ET` (keep `compute_et_date` logic intact) | T1 | Constant swap only; function body unchanged. Pinned by `tests/test_timeline_f25.py`. |
| 5 | Update 3 tests' monkeypatch targets (`today_et`→`et_today` in `test_steering_state.py`, `test_intraday_watch.py`) | T1 | Test follows the rename; behavior assertions unchanged. |

**T3 items: none.** The one thing that *could* have escalated — a site secretly relying on a
different zone — was checked: all 6 sites use the ET alias pair, proven equivalent. No human gate.

**Excluded (not dups):** `scheduler.py` string `timezone=` param, `kis_broker._KST`. See `1-baseline.md`.

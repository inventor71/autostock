# Unit Test Execution — Unit `intraday-redesign` (F3)

> Framework: `pytest` (+ `hypothesis` for property-based tests). Run from the worktree root with the shared venv.

## Run all F3 unit tests
```bash
cd /home/jihoonpark/Project/autostock/.claude/worktrees/intraday-redesign
/home/jihoonpark/Project/autostock/venv/bin/python -m pytest tests/test_intraday_*.py -q
# -> 65 passed
```

## Run the full regression (no-regression gate, NFR-6)
```bash
/home/jihoonpark/Project/autostock/venv/bin/python -m pytest -q
# -> 347 passed   (baseline 282 + 65 new; 0 regressions)
```

## F3 test modules (65 tests)

| Module | Tests | Covers |
|---|---|---|
| `test_intraday_records.py` | 9 | E1–E6 records; v1 condition vocab; fail-closed on unknown condition; `set` requires trigger |
| `test_intraday_fills.py` | 6 | broker `get_fills`: simulated no-op; Alpaca raw `/account/activities` parse, `after`/`activity_types`, id-dedup, NFR-4 failure→[]; **real-shape pin (R1)** |
| `test_intraday_snapshot.py` | 3 | snapshot `fills` payload once; `.fills.cursor` persisted; `last_snapshot` in-proc; first-run no history flood |
| `test_intraday_watch.py` | 7 | WatchStore active/cleared/expired; malformed-line skip; fired once/day; **ET-date rollover re-arm (V4)**; CLI smoke |
| `test_intraday_bars.py` | 10 | BarCache TTL routing + failure→cached; price/volume breach; **Hypothesis PBT** (threshold monotonicity + strict boundary) |
| `test_intraday_brief.py` | 5 | brief from snapshot only (no broker), human-context, held-from-snapshot, fail-closed empty snapshot, watch levels |
| `test_intraday_news.py` | 4 | new-headline diff, dedup-clears, last-seen persistence, provider-failure tolerance |
| `test_intraday_wake.py` | 9 | ReconcileWorker per-kind no-starve + timeout pass-through; new_fill/protective; **paused suppress / entries_halted drops entry_inducing (Q7=A, V5)**; coalesce drain; watch fire-once; pure classifier |
| `test_intraday_orchestrator.py` | 6 | `intraday_prompt(brief)` / `wake_prompt`; `run_intraday(brief)` injection; legacy held path; `run_wake` timeout |
| `test_intraday_wiring.py` | 4 | `_intraday` brief injection (steering on); **steering=None legacy fallback (NFR-8)**; components built; IntradayConfig.from_mapping |
| `test_intraday_integration.py` | 2 | wake path through the REAL worker (coalesced drain); **scheduled-turn skips while wake in-flight (V3)** |

## Property-based tests (Hypothesis)
- `breaches_atr` / `breaches_volume`: monotonic in magnitude, strict-`>` boundary not a breach. (`test_intraday_bars.py`)

## Touched-existing regression (confirm unchanged behavior)
```bash
/home/jihoonpark/Project/autostock/venv/bin/python -m pytest \
  tests/test_steering_turns.py tests/test_steering_runtime.py tests/test_steering_channel.py \
  tests/test_execution.py -q
```
These cover the files F3 modified (ReconcileWorker, runtime.publish_snapshot, broker base/alpaca) — all green.

## Notes
- Tests are deterministic and offline (no network/LLM): the `claude` session, broker activities, and yfinance are stubbed/monkeypatched.
- The only piece tests can't prove offline is the **real** Alpaca activities response shape — covered by R1 (live, see summary) and pinned via `test_alpaca_get_fills_parses_real_activities_shape`.

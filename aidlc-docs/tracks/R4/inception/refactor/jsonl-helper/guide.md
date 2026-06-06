# Pick-up guide — R4: JSONL record helper

**Status**: backlog (not started). Survey point base `ec2875c` (2026-06-06). Rebase before work.

## Why
The codebase persists everything as append-only JSONL (no DB — see [[codekb]] / architecture).
The *same* read loop and append line are re-implemented across ~15 sites, each with slightly
different empty-line / corruption handling. That drift is the real cost: a torn-write or empty-line
bug fixed in one log silently stays unfixed in the others.

## Evidence (call sites at survey time)
Run to refresh: `grep -rln 'json\.loads(line\|model_validate_json(line\|model_dump_json' src --include='*.py'`

**Readers** (`read_text().splitlines()` → strip → skip empty → parse → `except: continue`):
- `src/agent/turn_log.py:190`, `equity_log.py:99`, `trades_log.py:92`
- `src/agent/steering/runtime.py` (multiple: ~706/734/807)
- `src/surge/store.py` (via `_read_complete_lines`, lines 99/139)
- `src/early_session/{records.py,index_writer.py:89,__main__.py}`

**Writers** (`fh.write(json.dumps(rec) + "\n")` or `model_dump_json()`):
- `src/agent/{equity_log:85, trades_log:81, turn_log:174, journal}.py`
- `src/agent/steering/{channel,commands}.py`, `src/agent/intraday/watch_store.py`

## Variations to preserve (these are why it's not a blind sed)
1. **Parse flavor**: some use `json.loads` (→ dict), some `Model.model_validate_json` (→ pydantic).
   The helper must support both: `read_records(path, model=None)` (raw dicts) vs
   `read_records(path, model=SurgeRecord)` (validated).
2. **Corruption policy differs**: most do `except json.JSONDecodeError: continue`; `surge/store.py`
   does `except Exception: continue` AND uses `_read_complete_lines` to drop a **torn last line**
   (partial append from a crash). The helper should offer `skip_corrupt=True` and optionally a
   `complete_lines_only=True` mode (fold `surge._read_complete_lines` into the helper).
3. **Empty-line skip**: nearly all `strip()` and skip blanks — make that the default.
4. **Missing-file**: some return `[]` for absent path; make that the default (don't raise).
5. **Append durability**: a few writers flush/fsync or write via temp-rename (`index_writer.py`).
   Don't collapse the temp-rename atomic writers into the naive appender — keep `append_record`
   for the plain appenders only; leave atomic-rewrite sites alone or give them a separate helper.

## Proposed shape (decide in Stage 3)
```python
# src/core/jsonl.py
def read_records(path, model=None, *, skip_corrupt=True, complete_lines_only=False): ...
def append_record(path, rec) -> None:   # rec: pydantic model | dict; writes one line + "\n"
def iter_records(path, model=None, ...):  # generator variant for big logs (turn_log/equity_log)
```
Keep it dependency-light (`core` depends on nothing — layer rule).

## Behavior-preservation / tiering
Expect **all T1**. The only T-escalation risk: if you *unify* corruption handling (e.g. make a
`JSONDecodeError`-only site also swallow other exceptions), that changes behavior → T3, flag it.
Safer: pass each site its current policy via args so behavior is byte-identical.

## Test net
Lean on existing round-trip tests: `tests/test_logs.py`, `tests/test_surge_store.py`,
`tests/signals/test_records_roundtrip.py`. Add a `tests/test_jsonl.py` covering: blank-line skip,
torn-last-line drop, corrupt-mid-file skip, model vs dict, missing file → `[]`, append round-trip.

## Suggested migration order (one green commit each)
surge/store (richest: has the complete-lines logic to fold in) → equity_log → trades_log →
turn_log → early_session → steering readers. Writers last. Run the owning test after each.

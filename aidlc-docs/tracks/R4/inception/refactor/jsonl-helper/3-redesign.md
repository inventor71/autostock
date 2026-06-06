# Stage 3 — Redesign: src/core/jsonl.py

**Track**: R4 · **Date**: 2026-06-06 · **Tier**: fully T1

## Target module `src/core/jsonl.py` (depends on nothing — core layer)
```python
# promoted verbatim from src/agent/steering/jsonl.py (single source of truth):
def atomic_write_text(path, text) -> None: ...
def read_complete_lines(path, start_offset) -> tuple[list[str], int]: ...
class ByteCursor: ...

# NEW read-all/append helpers (the R4 dedup):
def read_records(path, model=None, *, warn_skip=False) -> list:
    """Read all complete records (oldest first). missing file → []. Blank lines
    skipped. Each line parsed via json.loads (model=None → dict) or
    model.model_validate_json (pydantic). Unparseable lines skipped (warn if
    warn_skip). A torn trailing line is unparseable → skipped (same net result as
    surge's explicit drop)."""

def append_record(path, rec) -> None:
    """parent.mkdir(parents=True, exist_ok=True); append one line:
    rec.model_dump_json() if it's a pydantic model else json.dumps(rec); + '\n'."""

def append_records(path, recs) -> None:
    """Same, many records in one open() (matches trades_log's append loop)."""
```

## `src/agent/steering/jsonl.py` → re-export shim
Keep the module + its docstring; body becomes:
`from src.core.jsonl import atomic_write_text, read_complete_lines, ByteCursor`
(+ `__all__`). All 13 importers and `tests/test_steering_records.py` keep working unchanged.

## Equivalence (why T1)
- Promotion (#1/#2): identical function objects, just a new home + re-export.
- `read_records(model=None)` body == the equity/trades/turn loop exactly (missing→[], strip,
  skip-empty, json.loads, skip-on-parse-error).
- `read_records(model=X, warn_skip=True)` body == surge's `_read_complete_lines`+parse net result
  (torn/unparseable dropped, warn preserved). Date filter stays in `SurgeStore`.
- `append_record`/`append_records` == the existing append blocks (parent.mkdir + write+"\n").
- surge writes keep atomicity by routing `_atomic_append` through the same `atomic_write_text`.

## Migration order (green per step)
1. `core/jsonl.py`: move the 3 primitives in + add 3 helpers. Add `tests/test_jsonl.py`. Run it.
2. `steering/jsonl.py` → shim. Run `tests/test_steering_records.py` + full import.
3. `equity_log` read+write → helpers. Run `tests/test_logs.py`.
4. `trades_log` read+write → helpers. Run `tests/test_logs.py`.
5. `turn_log` read+write → helpers. Run `tests/test_logs.py`.
6. `surge/store` reads → `read_records(model=…, warn_skip=True)`; `_atomic_append` →
   `atomic_write_text`; drop `_is_valid_json`/`_read_complete_lines`. Run `tests/test_surge_store.py`.
7. Full `pytest -q`.

## Rollback
Each file migrates independently; a failing characterization test names the file — revert just that
one. The shim keeps the old import path valid, so no big-bang.

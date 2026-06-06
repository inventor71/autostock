# Stage 4 — Implementation: src/core/jsonl.py

**Track**: R4 · **Branch**: refactor/R4 · **Date**: 2026-06-06 · **Tier**: T1 (behavior-preserving)

## What landed
| File | Change |
|------|--------|
| `src/core/jsonl.py` | **NEW** — promoted `atomic_write_text`/`read_complete_lines`/`ByteCursor` from steering + added `read_records(path, model=None, *, warn_skip=False)`, `append_record`, `append_records` |
| `src/agent/steering/jsonl.py` | now a **re-export shim** (`from src.core.jsonl import ...`) — all 13 importers + `test_steering_records.py` unchanged |
| `src/agent/equity_log.py` | `read_equity`→`read_records`; `record_equity` append→`append_record`; dropped `import json` |
| `src/agent/trades_log.py` | `read_trades`→`read_records`; append loop→`append_records`; dropped `import json` |
| `src/agent/turn_log.py` | `read_turns`→`read_records`; write→`append_record`; dropped `import json` |
| `src/surge/store.py` | `read_records`/`read_analyses`→core `read_records(model, warn_skip=True)`+date filter; `_atomic_append`→`atomic_write_text`; removed `_is_valid_json`/`_read_complete_lines` + `import json/os/uuid` |
| `tests/test_jsonl.py` | **NEW** — 10 unit tests for the helpers (missing→[], blank/corrupt/torn skip, dict vs model, append round-trip, empty no-op) |
| `tests/test_surge_store.py` | dropped the 2 removed-helper unit tests (behavior now in `test_jsonl.py`); kept `_atomic_append` + all store-behavior tests |

## Equivalence (why T1)
- **Promotion**: identical function objects, new home + re-export shim → zero change for 13 importers.
- **`read_records(model=None)`** body == the equity/trades/turn loop (missing→[], strip, skip-empty,
  parse, skip-on-error). The originals caught `json.JSONDecodeError`; the helper catches `Exception`,
  but `json.loads(str)` only raises `JSONDecodeError` so the caught set is identical for the dict path.
- **`read_records(model=X, warn_skip=True)`** net result == surge's `_read_complete_lines`+parse:
  torn/unparseable lines dropped (warned), date filter applied after. Only the *wording* of the warn
  log differs (generic vs "torn last line, dropping") — not observable behavior.
- **`append_record`/`append_records`** == the existing `parent.mkdir` + `open("a")` + `write(...+"\n")`.
- **surge writes** keep atomicity — `_atomic_append` now routes through the shared `atomic_write_text`
  (same temp + `os.replace`); durability preserved (NOT downgraded to plain append).

## Verification
- Targeted: `test_jsonl.py` + `test_logs.py` + `test_surge_store.py` + `test_surge_tools.py` +
  `test_steering_records.py` → **45 passed**.
- **Full suite** `pytest -q` → **984 passed, 0 failed**.
- `py_compile` clean; no stale refs to removed helpers; no leftover `import json`/`json.` in migrated files.

## Out of scope (recorded)
`src/early_session/{index_writer,records,__main__}.py` — deliberate `fsync` writer + `obj["symbol"]`
key-extraction reader. Left as-is (low dedup value, higher risk). Possible future pass.

## Critic pass (independent review vs 9e9aec2)
Promotion integrity, shim completeness, append format, lost symbols all verified byte-identical.
Findings:
- **[MEDIUM] fixed**: surge `_atomic_append` read existing content with locale-default
  `read_text()` while writing UTF-8 via `atomic_write_text` — an inconsistency I introduced. Made
  surge consistently **UTF-8** (read + write), matching pydantic's UTF-8 `model_dump_json` and the
  rest of the codebase. Deliberate, benign hardening (the original surge was locale-default and would
  itself mis-handle non-ASCII under a non-UTF-8 locale; identical on the UTF-8 deployment).
- **[LOW] accepted**: the 3 dict readers now `except Exception` (was `json.JSONDecodeError`), so a
  pathological `RecursionError` line is skipped rather than crashing the whole read — the intended
  "skip corrupt line" behavior for a telemetry log; not observable for normal data.
- **[LOW] accepted**: surge skip-warning wording/count differs (silent on mid-file blank lines now;
  generic message on a torn last line). Log-only — records returned are identical in every traced case.

## Post-merge guide: SKIPPED (purely internal)
No observable production behavior change — same file formats, same read/append/atomic semantics,
internal helper consolidation only.

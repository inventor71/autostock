# Tier Ledger — jsonl-helper (R4)

범위: new `src/core/jsonl.py`; `src/agent/steering/jsonl.py`→shim; migrate
`equity_log`/`trades_log`/`turn_log`/`surge/store`. 작성일: 2026-06-06

## T1 — 동작 보존 (자율 진행)
| # | 변경 항목 | 보존되는 동작 | 보존 검증 방식 | 근거 |
|---|-----------|---------------|----------------|------|
| 1 | Move `read_complete_lines`/`atomic_write_text`/`ByteCursor` → `src/core/jsonl.py` | same functions, same behavior | `tests/test_steering_records.py` (unchanged import path) | pure move |
| 2 | `src/agent/steering/jsonl.py` → re-export shim (`from src.core.jsonl import *`) | all 13 importers + test resolve identical names | full suite import + `test_steering_records.py` | re-export, no logic |
| 3 | Add `read_records(path, model=None, *, warn_skip=False)` to core | read-all: missing→[], blank-skip, parse, skip-on-error | new `tests/test_jsonl.py` | new helper |
| 4 | Add `append_record(path, rec)` / `append_records(path, recs)` | parent.mkdir + plain append `json.dumps`/`model_dump_json` + "\n" | new `tests/test_jsonl.py` | new helper |
| 5 | `equity_log.read_equity` → `read_records(path)` | list[dict], missing→[], skip blank/corrupt, order | `tests/test_logs.py` | byte-identical loop |
| 6 | `equity_log.record_equity` append → `append_record(path, snap)` | one appended line, parent.mkdir; returns snap | `tests/test_logs.py` | same append |
| 7 | `trades_log.read_trades` → `read_records(path)` | as #5 | `tests/test_logs.py` | byte-identical |
| 8 | `trades_log.record_trades` append loop → `append_records(path, new)` | same lines appended, only-new (dedup logic untouched) | `tests/test_logs.py` | same append |
| 9 | `turn_log.read_turns` → `read_records(path)` | as #5 | `tests/test_logs.py` | byte-identical |
| 10 | `turn_log` write → `append_record(path, rec)` | one appended line | `tests/test_logs.py` | same append |
| 11 | `surge.read_records`/`read_analyses` → `read_records(path, Model, warn_skip=True)` + date filter | torn-line dropped, unparseable skipped (warn), date filter, order | `tests/test_surge_store.py` | same parse loop |
| 12 | `surge._atomic_append` → use core `atomic_write_text` (read existing + rewrite) | atomic temp+replace durability preserved | `tests/test_surge_store.py` | same atomic primitive |
| 13 | Remove surge `_is_valid_json`/`_read_complete_lines` (folded into core `read_records`) | torn-last-line drop preserved (now via per-line skip = same result) | `tests/test_surge_store.py` | equivalent net result |

**보호 매핑**: #1/#2 → `test_steering_records.py`; #3/#4 → new `test_jsonl.py`; #5–#10 → `test_logs.py`;
#11–#13 → `test_surge_store.py`. 공백(#3/#4 helper 자체) → 단계 1에서 `test_jsonl.py` 추가.

## T2 — 안전한 확장
(none — no new optional paths.)

## T3 — 의도 변경 / 기능 cut (🛑 승인 필요)
**None.** All-T1. Two log-only nuances are NOT behavior changes (no functional/output change):
- surge's "torn last line, dropping" warning becomes a generic per-line skip (with `warn_skip=True`
  the skip still warns). Net records returned are identical.
- the dict readers caught `json.JSONDecodeError`; core `read_records` catches `Exception` — for the
  `model=None` path `json.loads(str)` only raises `JSONDecodeError`, so the caught set is identical.

## 정지 지점
- [x] T3 항목 없음 — 게이트 통과, 자율 진행 (per autonomy-in-construction)
- [x] 단계 1 `test_jsonl.py` 작성 + green (10 tests)
- [x] 단계 3 redesign (`3-redesign.md`) → 단계 4 구현 (`4-implementation.md`) — full suite 984 passed

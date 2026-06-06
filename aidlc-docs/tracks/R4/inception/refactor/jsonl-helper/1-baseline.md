# Stage 1 — Baseline: JSONL record helper

**Track**: R4 · **Base**: 9e9aec2 (main HEAD at pick-up) · **Date**: 2026-06-06

## 1. Current landscape (corrects the survey-time guess)
The survey said "no shared helper". **There already is one** —
`src/agent/steering/jsonl.py` provides the *torn-safe + atomic* primitives:
- `read_complete_lines(path, start_offset) -> (lines, new_offset)` — byte-cursor reader (cross-process safe)
- `atomic_write_text(path, text)` — temp + `os.replace`
- `ByteCursor` — persisted byte offset

**13 importers** already use it (journal, executor, self_rewrite, quality/collector,
intraday/{news_diff,watch_store}, steering/{state,channel,commands,runtime}, + `tests/test_steering_records.py`).
So journal + steering + intraday are **already DRY**. Two issues remain:
1. It lives under `src/agent/steering/` — an awkward home for something `core`-level that `surge` and
   the agent logs could also use (layer rule: `core` depends on nothing).
2. The **simple read-all/append dict pattern** is still duplicated outside it.

## 2. The actual duplication (R4 target)
Three nearly **byte-identical** read-all readers + their appends:

| File | reader | writer |
|------|--------|--------|
| `src/agent/equity_log.py` | `read_equity` (89-107) | `record_equity` append (84-85) |
| `src/agent/trades_log.py` | `read_trades` (87-99) | `record_trades` append (78-81) |
| `src/agent/turn_log.py` | `read_turns` (185-196) | append (172-174) |

All three readers are identical modulo names:
```python
if not path.exists(): return []
for line in path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line:
        try: out.append(json.loads(line))
        except json.JSONDecodeError: continue
```
All three writers: `path.parent.mkdir(parents=True, exist_ok=True)` + `open("a")` + `write(json.dumps(x)+"\n")`.

Plus `src/surge/store.py` has its **own** parallel implementations: `_is_valid_json`,
`_read_complete_lines` (drops torn last line + warns), `_atomic_append` (temp + `os.replace` — a 2nd
copy of `atomic_write_text`), and two model-based read loops (`read_records`/`read_analyses`, 96-148).

## 3. Preserved observable contract (per file)
- `read_equity/read_trades/read_turns(path) -> list[dict]`: missing file → `[]`; blank lines skipped;
  unparseable lines skipped (no raise); order preserved (oldest first).
- `record_equity/record_trades/turn append`: creates parent dir; appends one JSON line each; does NOT
  rewrite the file (plain append).
- `SurgeStore.read_records/read_analyses(d=None) -> list[Model]`: torn last line dropped (warn);
  unparseable lines skipped (warn); optional date filter; order preserved.
- `SurgeStore.write_records/append_analysis`: **atomic** (temp + `os.replace`), dedup-by-key for
  records; durability must be preserved (NOT downgraded to plain append).
- `steering/jsonl.py` public names (`read_complete_lines`, `atomic_write_text`, `ByteCursor`) must
  keep resolving for all 13 importers + the test.

## 4. Out of scope (this track)
- `src/early_session/{index_writer,records,__main__}.py` — its writer deliberately `fsync`s before
  `os.replace` (a stronger durability guarantee than `atomic_write_text`), and its reader extracts
  `obj["symbol"]` with a specific `KeyError` skip. Low dedup value, higher risk → leave as-is (note
  for a possible future pass).
- `journal.py` / `steering/*` / `intraday/*` — already DRY via the helper; only benefit transitively
  from the promotion (no edits).

## 5. Test coverage (characterization baseline)
- `tests/test_logs.py` — exercises equity/trades/turn read+write round-trips.
- `tests/test_surge_store.py` — surge read/write incl. torn-line + dedup.
- `tests/test_steering_records.py` — `read_complete_lines`/`atomic_write_text`/`ByteCursor`.
Gap to close in Stage 1: a direct `tests/test_jsonl.py` for the new `core/jsonl` helpers
(missing-file→[], blank skip, corrupt skip, model vs dict, append round-trip) so the helper itself
is locked independent of its call sites.

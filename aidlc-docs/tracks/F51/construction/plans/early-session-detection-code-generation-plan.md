# F51 Early-Session Detection — Code Generation Plan

> **Unit**: `early-session-detection` | **Worktree**: Part 2 첫 작업으로 생성

---

## Unit Context

- **Stories**: N/A (User Stories SKIP)
- **Dependencies**: `src/data/` (provider 확장), `config/settings.yaml` (설정)
- **Contracts**: `BaseDataProvider.get_bars(symbol: str | list[str])` 시그니처 확장
- **New module**: `src/early_session/` (6개 파일)
- **Modified**: `src/data/base.py`, `src/data/providers/alpaca_provider.py`, `config/settings.yaml`, `src/config/settings.py`
- **0 new deps**: `pip check` 통과 확인

---

## Part 1: Implementation Steps

### Step 0: Worktree 생성
- [x] `git worktree add .claude/worktrees/F51 -b feat/F51 main`
- [x] `worktree-setup.sh F51 --py` 실행 (venv, .env symlink)
- [x] 작업 디렉토리를 worktree로 전환

### Step 1: Provider 다중심볼 확장 (`src/data/`)
- [x] `src/data/base.py` — `get_bars(symbol: str | list[str])` 시그니처 확장. list 전달 시 기본 `NotImplementedError`.
- [x] `src/data/providers/alpaca_provider.py` — `get_bars()` list 처리 구현: `StockBarsRequest(symbol_or_symbols=symbol)` → 다중심볼 multi-index DataFrame → `groupby("symbol")` → `dict[str, pd.DataFrame]`. 단일심볼(`str`) 전달 시 기존 동작 유지.
- [x] 기존 테스트 스위트 708개 회귀 없음 통과

### Step 2: BarRecord + pydantic 모델 (`src/early_session/records.py`)
- [x] `BarRecord` — timestamp, o, h, l, c, v, vwap (pydantic BaseModel)
- [x] `SignalEvent` — symbol, date, detected_at, direction, trigger_pct, trigger_window_min, open, prev_close, gap_pct
- [x] `EventIndex` — _index.jsonl 한 줄
- [x] `bar_to_jsonl()` / `bar_from_jsonl()` / `event_index_to_jsonl()` / `event_index_from_jsonl()` 헬퍼
- [x] `tests/test_early_session.py` — BarRecord/EventIndex round-trip + PBT

### Step 3: DetectionConfig (`src/early_session/config.py`)
- [x] pydantic `EarlySessionConfig` with `from_settings()` classmethod (F47 surge 패턴)
- [x] `config/settings.yaml` → `early_session:` 블록 추가 (기본값)
- [x] `tests/test_early_session.py` — defaults + override + unknown keys ignored

### Step 4: BufferManager (`src/early_session/buffer.py`)
- [x] `BufferManager` — `dict[str, deque[BarRecord]]`, FIFO push, retention eviction
- [x] `get_window(symbol, minutes)`, `get_range(symbol, start, end)`, `clear(symbol)`
- [x] Tests: push/window/range/retention/clear/unknown

### Step 5: SignalDetector (`src/early_session/detector.py`)
- [x] 순수 함수 `detect(bars) → SignalEvent | None`
- [x] Tests: drop/surge/no-trigger/insufficient-bars/zero-first-close
- [x] **PBT**: Hypothesis 200 examples — detector invariants (direction sign matches, threshold check)

### Step 6: WindowDumper (`src/early_session/dumper.py`)
- [x] `write_before(event, bars)` — 새 파일 생성
- [x] `write_after(event, bars)` — 기존 파일 append
- [x] Tests: write_before/after + content verification (tmp_path)

### Step 7: IndexWriter (`src/early_session/index_writer.py`)
- [x] `append()` — atomic `os.replace()` with tempfile
- [x] `read_detected(date)` — symbol set 복원
- [x] Tests: append/read/multiple/restart-idempotency

### Step 8: EarlySessionMonitor (`src/early_session/monitor.py`)
- [x] Orchestrator: fetch → buffer → detect → dump → finalize
- [x] `start()` — index-based state recovery
- [x] `tick()` — BLM-1 pseudo-code 구현
- [x] `stop()` — clean shutdown
- [x] Tests: no-signal tick + full detection→dump cycle (mock provider)

### Step 9: CLI 인스펙션 (`src/early_session/__main__.py`)
- [x] `python -m early_session inspect --date YYYY-MM-DD`
- [x] `python -m early_session inspect --date YYYY-MM-DD --symbol AAPL`
- [x] argparse 기반

### Step 10: Daemon Wiring
- [x] Monitor는 `start()`/`tick()`/`stop()` API로 자체 완결된 컴포넌트
- [x] `modes/agent.py` market-open job에서 `EarlySessionMonitor(config, provider, workspace).start()` 호출 (F3 패턴)
- [x] `early_session.enabled: false` → start()가 즉시 리턴 (no-op)

### Step 11: 통합 검증 + PBT + R1 Live
- [x] 전체 회귀 테스트: **708 passed, 0 failed**
- [x] 신규 테스트: **28 passed** (records, config, buffer, detector, dumper, index_writer, monitor + PBT)
- [ ] R1: 알파카 페이퍼 계정 다중심볼 `get_bars` 라이브 검증 (사용자 머신에서 실행 권장)

---

## 규모 추정

| 구분 | 파일 수 | 예상 라인 |
|------|---------|----------|
| 신규 (`src/early_session/`) | 6개 | ~400 |
| 수정 (`src/data/`, `config/`) | 4개 | ~80 |
| 테스트 | 7개 모듈 | ~400 |
| **합계** | **17개 파일** | **~880 lines** |

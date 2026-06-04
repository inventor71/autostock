# F56 Code Generation Plan (single bugfix unit)

> Worktree: `.claude/worktrees/F56` (branch `feat/F56`). 코드는 worktree에서만.

## Code changes
- [x] **C-1 (FR-1)** `src/data/base.py::get_daily_bar` — 조회구간 `d-7d`로 확대, 날짜 `d` 행을 today,
      직전 행을 prev_close로 매핑(마지막 행이 d가 아닐 수 있으니 날짜로 탐색).
- [x] **C-2 (FR-2)** `src/early_session/monitor.py` — `_ET=ZoneInfo("America/New_York")`,
      `start()`/`tick()`의 now·monitor_end·day-start를 ET 기준으로.
- [x] **C-3 (FR-3)** `src/agent/executor.py::execute_pending` — `kept` 외 pending 인덱스(슈퍼시드)를
      `terminal_indices`에 추가 → cursor 전진.
- [x] **C-4 (FR-4+BUG-6)** `monitor.py` — `_pending_finalizes: dict[str, tuple[SignalEvent, datetime]]`,
      finalize에서 보관 event 사용, 죽은 재감지/`first_bar` 분기 제거.
- [x] **C-5 (FR-5)** `early_session/config.py`에 `effective_retention_minutes` 도출 프로퍼티 +
      `monitor.py`가 그 값으로 BufferManager 생성 + `config/settings.yaml` 기본값 75로 정합화.
- [x] **C-6 (FR-6)** `monitor.py` 생성자에 `symbols` 주입(콜러블/리스트, fallback `config.config`),
      `_symbols()` 수정(깨진 `src.config.settings` import 제거) + `src/trading/modes/agent.py::start`에
      `_setup_early_session()` 등록(enabled 가드, market-open start + seconds tick, universe 주입).
      추가: `_setup_early_session`/`_run_surge_scan`이 `load_yaml_config`로 yaml 블록을 직접 읽도록
      수정(Settings(extra="ignore")가 surge/early_session 블록을 버리던 문제 — `enabled` 게이트가
      실제로 동작하도록).

## Tests (`tests/test_f56_bugfixes.py`)
- [x] get_daily_bar prev_close + surge end-to-end (C-1)
- [x] cursor 전진/재시도-정지/비재실행 3종 (C-3)
- [x] ET monitor_end(C-2), finalize 보관 무크래시(C-4), effective retention(C-5), symbols 주입(C-6)
- [x] PBT(Partial): `_calculate_change`, EventIndex JSONL 라운드트립 (detect/bar PBT는 기존 파일에 존재)
- [x] 회귀: 전체 728 passed

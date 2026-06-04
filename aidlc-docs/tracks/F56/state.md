# Track F56 — code-review 후속 버그 수정 (F47/F51/F52)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F56
- **Title**: code-review 후속 버그 수정 — surge prev_close, early-session ET/finalize/retention, executor cursor stall
- **Type**: feature (bugfix)
- **Status**: merged → main 6b043c6 (2026-06-04)
- **Branch**: feat/F56
- **Worktree**: .claude/worktrees/F56
- **Submodule branch**: — (operator-console/cli 미변경 예정)
- **Base commit**: 6bf1b31
- **Start Date**: 2026-06-03T16:06:17Z

## Extension Configuration
- **Security Baseline**: Disabled — 사용자 opt-out. 내부 버그 수정으로 새 공격 표면 없음(외부 입력/네트워크/인증 변경 없음); thesis 파일 읽기는 이미 fail-closed.
- **Property-Based Testing**: Enabled (Partial) — 순수 함수(`SignalDetector.detect`, `SurgeDetector._calculate_change`)와 JSONL 직렬화 라운드트립(`bar_to_jsonl`/`bar_from_jsonl`, `event_index_*`)에만 PBT 적용. framework=Hypothesis.

## Scope
직전 `/code-review` (범위 `c76d682..faec7b7`, 최근 머지된 F51/F53/F52/F47/F50 트랙)에서 검출한
실제 버그 수정. 동작 변경이 아니라 "원래 의도대로 동작하게" 만드는 수정.

대상 버그(심각도 순):
- **BUG-1 (High)** `src/data/base.py` `get_daily_bar()` — 조회 구간이 당일 1일뿐이라 `prev_close`가
  항상 `None`. → `SurgeDetector`가 모든 종목을 임계 미달로 처리 → F47 surge 스캔이 영구 0건.
- **BUG-2 (High)** `src/early_session/monitor.py` `start()` — `monitor_end_et`("ET")를 UTC `now`에
  그대로 적용 → 잘못된 종료시각(첫 tick에 즉시 stop 가능). ET→UTC(또는 ET-aware) 변환 필요.
  (`monitor_start_et`도 현재 미사용.)
- **BUG-3 (Med-High)** `src/agent/executor.py` `execute_pending()` — latest-by-symbol dedup으로
  밀려난 인덱스가 `terminal_indices`에 들어가지 않아 cursor 전진 루프가 거기서 영구 정체.
  → `pending`/`terminal_indices` 세션 내 무한 증가. dedup으로 건너뛴 인덱스도 terminal 취급 필요.
- **BUG-4 (Med)** `src/early_session/monitor.py` finalize — 재감지가 None인데 `after_bars`가 있으면
  `event=None`이 `write_after()`/`index_writer.append()`로 전달 → `AttributeError` 매 tick 반복.
- **BUG-5 (Med)** `config/settings.yaml` early_session — `buffer_retention_minutes(20)` <
  `dump_after_minutes(45)`. finalize 시 after-window 앞부분 유실, `bar_count` 과소 계산.
  보존시간이 `dump_before + dump_after` 이상이 되도록 조정(또는 retention 도출).
- **BUG-6 (Low, cleanup)** `monitor.py` finalize의 죽은/꼬인 복구 분기(`first_bar` 미사용,
  동일 윈도우 재감지) 단순화/제거.

비고: `src/early_session/` 모듈(F51)은 아직 스케줄러에 미연결(latent). BUG-2/4/5/6은 연결 시점에
드러남. BUG-1/3은 이미 활성 경로(EOD surge 스캔, executor 커서).

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성. `/ai-dlc-merge`가 큐 구성·충돌 해결 시 참조.

- **공유 파일 (주의)**: `src/data/base.py`, `src/agent/executor.py` — 다른 활성 트랙(F54 숏 기능 등)이
  executor/data provider를 건드릴 수 있음. F54가 `executor.py`를 수정하면 rebase 시 수동 조정 가능.
- **API/시그니처 변경**: 없음 예정(내부 로직 수정만). `get_daily_bar` 시그니처 유지.
- **알려진 동시 변경**: F54(숏 매매, executor/risk 영역 가능성), F30(KIS 브로커, data provider 영역).

## Stage Progress
- [x] Workspace Detection — brownfield, 기존 RE 아티팩트 존재 → Reverse Engineering 스킵
- [x] Requirements Analysis — standard (6 버그 + 모니터 연결) → `inception/requirements/requirements.md`
- [x] User Stories — skip (사용자 향 신규 기능 아님, 내부 버그 수정)
- [x] Workflow Planning → `inception/plans/execution-plan.md`
- [x] Application Design — skip (신규 컴포넌트 없음)
- [x] Units Generation — skip (단일 유닛)
- [x] Construction (per-unit Code Generation) — C-1~C-6 → `construction/plans/code-generation-plan.md`
  - [x] bugfix unit — 6개 버그 수정 + 모니터 연결 + 테스트 (`tests/test_f56_bugfixes.py`)
- [x] Build & Test — 728 passed → `construction/build-and-test/build-and-test-summary.md`

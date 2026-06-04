# F56 Execution Plan (Workflow Planning)

## 실행할 단계 (적응형)
| 단계 | 실행 | 근거 |
|------|------|------|
| Workspace Detection | ✅ done | brownfield, RE 아티팩트 존재 → RE 스킵 |
| Requirements Analysis | ✅ done (standard) | 6 버그 + 모니터 연결 |
| User Stories | ⏭ skip | 사용자 향 신규 기능 아님(내부 버그/통합) |
| Workflow Planning | ✅ this doc | 항상 |
| Application Design | ⏭ skip | 신규 컴포넌트 없음(기존 클래스 수정 + 기존 스케줄러 패턴 재사용) |
| Units Generation | ⏭ skip | 단일 유닛 |
| Functional Design | ⏭ skip | 신규 비즈 로직 없음 — 버그 수정 + 기존 패턴 연결 |
| NFR Requirements/Design | ⏭ skip | 기술 스택 확정, PBT는 Extension으로 처리 |
| Infrastructure Design | ⏭ skip | 인프라 변경 없음 |
| Code Generation | ✅ always | 단일 유닛 — 아래 변경 목록 |
| Build & Test | ✅ always | 단위 + PBT(Partial) + 회귀 |

## Construction 변경 목록 (단일 유닛: bugfix)

### C-1 (FR-1) `src/data/base.py` — `get_daily_bar`
- 조회 구간을 `start = datetime(d) - 7일`, `end = datetime(d) + 1일`로 확대(공휴일/주말 대비).
- 반환 일봉에서 날짜 `d`에 해당하는 행을 "today", 그 직전 행을 prev_close로 매핑.
  - 단일/멀티 인덱스 모두 단일-symbol 경로(`get_bars(str,…)`)로 호출 → DataFrame.
  - 마지막 행이 `d`가 아닐 수도 있으므로 인덱스 날짜로 today 행을 찾고, 그 앞 행을 prev로.
  - prev 행이 없으면 `prev_close=None` 유지(기존 계약).
- 시그니처/반환 dict 키 불변(`open/high/low/close/volume/prev_close`).

### C-2 (FR-2) `src/early_session/monitor.py` — ET 시각 일관화
- 모듈 상단 `_ET = ZoneInfo("America/New_York")` 추가, `UTC` 사용 제거(또는 ET로 대체).
- `start()`: `now = datetime.now(_ET)`, `monitor_end = now.replace(h, m, tz 유지)`.
- `read_detected` 날짜 키, tick의 "오늘 0시" 기준도 ET로 통일.
- 버퍼/디텍터의 bar 타임스탬프는 provider가 주는 tz-aware 값과 비교 — aware끼리 비교 보장.

### C-3 (FR-3) `src/agent/executor.py` — cursor 전진 정합화
- `execute_pending()`에서 `kept = {idx for idx,_ in batch}` 계산.
- pending 범위(`cursor..len`)에서 `kept`에 없는 인덱스(= 슈퍼시드 중복)를 `terminal_indices`에 추가.
- 기존 contiguous-prefix 전진 루프 유지 → 재시도 대상(no_order/error)인 최신 결정만 cursor를 멈춤.
- terminal 재실행 금지(active_batch 필터) 유지.

### C-4 (FR-4+BUG-6) `src/early_session/monitor.py` — finalize event 보관
- `_pending_finalizes: dict[str, datetime]` → `dict[str, tuple[SignalEvent, datetime]]`.
- 감지 시 `(event, finalize_at)` 저장. finalize에서 저장된 event 직접 사용.
- 죽은 재감지/`first_bar` 복구 분기 전면 삭제.

### C-5 (FR-5) `src/early_session/{config,monitor}.py` + `config/settings.yaml`
- 유효 보존시간 = `max(buffer_retention_minutes, dump_before + dump_after + window + margin)`을
  모니터가 BufferManager 생성 시 도출(또는 `EarlySessionConfig`에 pydantic validator로 보장).
- `settings.yaml`의 `buffer_retention_minutes` 기본값을 정합 값(예: 75)으로 갱신 + 주석.

### C-6 (FR-6) `src/trading/modes/agent.py` (+ 필요 시 `monitor.py` 생성자)
- `start()`에 early_session 잡 등록(enabled 가드). market-open `start` + seconds `tick`.
- `EarlySessionMonitor`에 universe 주입 경로 추가(생성자 `symbols`/콜러블 또는 `executor.universe`).
- import/조립은 기존 `_run_surge_scan`/intraday 패턴과 동일하게 지연 import + best-effort.

### 테스트 (Build & Test)
- `tests/` 단위: get_daily_bar prev_close(C-1), executor cursor 시나리오 3종(C-3),
  monitor ET stop(C-2)·finalize 보관(C-4)·버퍼 보존(C-5), 스케줄러 잡 등록(C-6, 모킹).
- PBT(Partial, Hypothesis): `detect` 임계 성질, `_calculate_change`, JSONL 라운드트립.
- 회귀: 기존 `tests/test_early_session.py`, `tests/test_surge_*.py`, `tests/test_executor.py` 통과.

## Worktree 게이트
- Code Gen Part 2 전 `scripts/worktree-setup.sh F56 --py` (또는 `git worktree add
  .claude/worktrees/F56 -b feat/F56`). 코드는 worktree에서만 작성.

## Merge Risk
- 공유 파일 `src/agent/executor.py`(F54와 겹칠 수 있음), `src/data/base.py`(F30/data provider).
- 시그니처 불변 → rebase 충돌 위험 낮음.

# F44 워크플로 계획 + 유닛 분해

## 실행할 단계 (적응형)
| 단계 | 실행 | 사유 |
|------|------|------|
| Workspace Detection | ✅ | brownfield 확인 완료 |
| Reverse Engineering | ⏭ skip | 기존 아티팩트/트랙 다수, 해당 코드 영역 이미 파악 |
| Requirements Analysis | ✅ standard | `inception/requirements.md` |
| User Stories | ⏭ skip | 운영자 1인, 워크플로 변화 작음(라벨 1줄 + dedup 분기) |
| Workflow Planning | ✅ | 본 문서 |
| Application Design | ⏭ skip | 신규 컴포넌트 없음 — 기존 TurnCoordinator/runtime/TimelineBar 경계 내 |
| Units Generation | ✅ | 2 units (아래) |
| Construction (per-unit) | ✅ | Functional/NFR/Infra design은 unit별 최소(skip 가능), Code Gen always |
| Build & Test | ✅ | pytest + tui-trading + turbo typecheck |

## 유닛 분해
### Unit 1 — turn-dedup (daemon, Python)
- **TurnCoordinator**(`turns.py`): `start_priority_async`에 `dedup_key` 추가 +
  `_pending_keys: set[str]` (대기/실행 중 manual key) 를 `_waiters_lock`로 보호.
  - enqueue 진입(락 하): `running_key == dedup_key` → `"already_running"`;
    `dedup_key in _pending_keys` → `"already_queued"`; 아니면 추가 후 기존 흐름.
  - 스레드 종료 시 finally에서 `_pending_keys`에서 제거.
  - 대기 kind 노출: `queued_kinds()`(=_pending_keys − 현재 실행 kind) 프로퍼티.
- **runtime**(`runtime.py`): `_trigger_turn`이 `running_key=(self._current_turn or {}).get("type")`
  를 넘겨 dedup; `publish_monitor`에 `queued`(수) 또는 `queued_turns`(목록) 필드 추가(FR-B5).
- **commands**(`commands.py`): `_v_research`가 `already_running`/`already_queued` outcome을
  운영자 메시지로 emit(FR-B1/B2).
- **tests**: `tests/test_turn_dedup.py` — 단위 + **property-based**(hypothesis) 불변식
  "무작위 트리거 시퀀스에서 동일 type이 동시에 _pending에 2개 들어가지 않음 / 동일 type running 중 트리거는 always rejected".

### Unit 2 — progress-label (TUI, tui-trading)
- **types.ts / use-monitor-data.ts**: monitor의 `queued`(수)를 `MonitorData`에 노출.
- **timeline-bar.tsx**: TickRow 위(또는 전용 상태줄)에 한 줄 추가 —
  `● {type} · {elapsed} · +{N} queued`. `started_at`→경과는 기존 blink 타이머/clock 재사용.
  유휴 시 빈 줄/`idle`, 과거 날짜 미표시(now-cursor와 동일 게이트).
- **tests**: `operator-console/cli/packages/tui-trading/test/progress-label.test.ts` —
  type/elapsed/queued 포맷 + 유휴/과거날짜 분기.

## 순서 / 의존성
- Unit1(daemon)이 `queued` 필드를 monitor.json에 발행 → Unit2(TUI)가 소비.
  Unit1 먼저, 이어서 Unit2. 둘 다 한 worktree(F44)에서 진행.

## Worktree 게이트
- 코드 생성(Code Gen Part 2) 전 `scripts/worktree-setup.sh F44 --ts` (TS 콘솔 포함 →
  bun install + tsgo 확보, main `.env` 링크). 이후 worktree 안에서만 코드 변경.

## 검증
- daemon: `pytest`(dedup + property-based) — main venv.
- TUI: worktree에서 `bun run typecheck`(tsgo) + `tui-trading` 테스트.
- 통합: (선택) docker-verify smoke 또는 라이브 재시작 후 `/research` 2회 → 두 번째 `already_*`,
  상태줄에 `● research · …` 노출 확인.

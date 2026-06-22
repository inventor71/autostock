# Track F76 — thesis torn-read 완화 + write_position footgun 제거 (lean bugfix)

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`. Lean 트랙 — full AI-DLC 스테이지
> 생략, 이 stub + audit가 per-track 기록.

## Track Info
- **Track ID**: F76
- **Title**: positions thesis torn-read 완화 (filedrop stat-stable read) + `Journal.write_position` 원자화
- **Type**: bugfix (lean)
- **Status**: merged → main 366a6a8 (2026-06-22)
- **Branch**: feat/F76 (rebased 23212f5→5c47f46 → merged 366a6a8)
- **Worktree**: .claude/worktrees/F76 (제거됨)
- **Base commit**: 23212f5 → rebased onto 1b5eb40
- **Start Date**: 2026-06-12T12:39:47Z

## Scope (2건, 둘 다 소규모)

### 1. TUI thesis 찢긴 읽기 (실재 버그, LOW)
- **현상**: `operator-console/src/filedrop.ts:135-143` `readThesis`가 `workspace/positions/<SYM>.md`를
  보호 없는 plain `readFileSync`로 읽음. 실제 작성자는 PM 에이전트 자신(claude CLI Write/Edit 도구,
  `src/agent/prompts.py:103,140`이 지시) — 쓰기 원자성을 우리가 통제 못함. 데몬 턴 중 TUI(F53
  thesis 노출)에서 읽으면 잘린 마크다운 표시 가능.
- **수정 방향**: 리더 측 **stat-stable read** — 읽기 전후 mtime/size 비교, 변했으면 재시도(상한 N회).
  `orchestrator.py:449`의 positions `copytree`도 같은 레이스 노출 — 검토 후 필요 시 동일 보강.
- **검증**: bun test (쓰기 중 읽기 시뮬레이션 픽스처).

### 2. `Journal.write_position` footgun (예방, 죽은 코드)
- **현상**: `src/agent/journal.py:223-225` 비원자 `write_text`. 현재 src/ 호출자 0개이나
  미래 채택 시 비원자 쓰기 부활.
- **수정 방향**: `src/core/jsonl.py:32`의 `atomic_write_text` 사용으로 교체 (snapshot 쓰기와
  동일 패턴). 또는 진짜 불용이면 삭제 — 착수 시 판단.
- **검증**: pytest (기존 journal 테스트 + 원자성 단위 테스트).

## 출처
F73(viz-shell) critic 라운드(2026-06-12)에서 발견 — viz-shell 없이도 성립하는 기존 표면
문제라 사용자 지시로 독립 lean 트랙 격상. 상세 분석: `aidlc-docs/tracks/F73/audit.md`
critic round 항목.

## Merge Risk Notes
- **공유 파일**: `operator-console/src/filedrop.ts` (F71 PWA·F72 screening이 최근 만짐 —
  최신 main에서 분기할 것), `src/agent/journal.py`
- **API/시그니처 변경**: 없음 (내부 구현만)
- **알려진 동시 변경**: F74/F75 활성 (내용 미상) — 분기 전 `git log` 확인

## Stage Progress (lean)
- [x] 구현 (worktree 생성 → 수정 2건 + 테스트) — 2026-06-18
  - ① `filedrop.ts` `readThesis` → 비공개 `readStable()` 경유(전후 stat size/mtime 비교, 최대 5회 재시도, best-effort).
  - ② `journal.py` `write_position` → `atomic_write_text` (temp+os.replace, redundant mkdir 제거).
  - ③ orchestrator copytree(`_create_isolated_workspace`): **스코프 제외** — 일회성 subagent
    워크스페이스로의 복사이고 실제 writer(claude CLI Write 툴)가 비원자라 리더측 재시도로는
    창을 좁힐 뿐 닫지 못함. 저가치로 판단, 미보강.
- [x] 검증 — filedrop bun test 8 pass(신규 stat-stable 포함), test_agent.py 55 pass(신규
  원자성 테스트 포함), operator-console/cli typecheck 19 ok. (full bun suite는 daemon/MCP
  통합 테스트가 라이브 프로세스 요구로 hang — F76 무관, 변경 격리됨.)
- [x] merge-awaiting 전환 — 2026-06-18

## Post-Merge Guide
**Skip** — 순수 내부 robustness 변경(찢긴 읽기 완화 + 죽은 코드 footgun 제거). 정상 운영에서
관측 가능한 새 동작/설정/env 없음. 실데이터 스모크 불요.

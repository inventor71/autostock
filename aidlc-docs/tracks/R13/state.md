# Track R13 — `tests/` 네이밍·구조 정비

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: R13
- **Title**: 트랙ID 기반 테스트명을 행동/모듈 기반으로 + `src/` 구조 미러링 규칙 수립
- **Type**: refactor
- **Status**: backlog  <!-- not started; pick up via /ai-dlc-refactor R13 -->
- **Branch**: refactor/R13 (TBD)
- **Worktree**: .claude/worktrees/R13 (TBD)
- **Submodule branch**: — (Python only, 테스트)
- **Base commit**: 2a4e02f (survey point; rebase when picked up)
- **Start Date**: TBD

## Extension Configuration
- **Security Baseline**: N/A (테스트 파일 개명·이동만).
- **Property-Based Testing**: N/A.

## Scope
테스트 명명이 두 갈래다(점검 #2 HIGH + #7 MEDIUM):
- **트랙ID 기반 이름**(무엇을 검증하는지 불명, F-번호는 머지 후 휘발): `test_f14.py`,
  `test_f56_bugfixes.py`, `test_monitor_f22.py`, `test_sidebar_status_rich.py`, `test_sidebar_upgrade.py` 등.
- **구조 불일치**: 73개 평면 + 3개만 서브디렉터리(`benchmark/` `signals/` `refactor/`).
  `test_intraday_*.py` 12개 등은 서브디렉터리 후보.

**테스트 내용 불변 — 이름·위치만 변경(순수 T1)**:
- 트랙ID 테스트를 행동/모듈 기반으로 리네임(예: `test_f14.py` → 검증 대상 이름;
  Stage 1에서 각 파일의 실제 검증 대상 조사해 매핑).
- `src/` 미러링 규칙 수립: 패키지별 `tests/<pkg>/` 서브디렉터리(예: intraday 테스트 묶기).
- 의미불명한 **테스트 함수명**도 정합.

**전수검사 (요구사항)**: 리네임/이동이 `pytest` 수집·CI 설정·`conftest`·상대 import·`-k` 필터·
문서 참조를 깨지 않는지 `rg`로 전수 확인. `python -m pytest`로 수집 수(count) 동일·green 유지.

## Merge Risk Notes
- **공유 파일 (주의)**: `tests/**` 전역.
- **API/시그니처 변경**: 없음(테스트 파일/함수명·경로만).
- **알려진 동시 변경 / 권장 순서**: R8~R12가 **각자 자기 테스트를 이동/개명**하므로 충돌 최소화를 위해
  **R13은 최후에 실행**(앞 트랙들이 정리한 최종 테스트 집합 위에서 명명·구조만 마감).

## Stage Progress (skill: ai-dlc-refactor)
- [ ] Stage 1 — Baseline (각 트랙ID 테스트의 실제 검증 대상 조사 → 리네임 매핑; 현 수집 수 기록)
- [ ] Stage 2 — Tier ledger (all-T1 — 이름/위치만)
- [ ] Stage 3 — Redesign (명명 규칙 + 서브디렉터리 미러링 규칙 + 리네임 매핑표 확정)
- [ ] Stage 4 — Implementation (개명/이동 + 수집·import·CI 참조 전수 갱신)
- [ ] Build & Test (수집 수 동일·전체 green 확인)

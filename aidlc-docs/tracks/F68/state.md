# Track F68 — F67 follow-up (자가학습 스택 정리)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F68
- **Title**: F67 follow-up — 자가학습 스택 정리: rollback-rewrite 순서(#7) + collect_outcomes EOD 캐시(#8) + is_meaningful 제거/임계 단일화(#10)
- **Type**: feature (follow-up / cleanup)
- **Status**: merged → main 9eaf8a0 (2026-06-06)  <!-- /ai-dlc-merge: rebased onto af2cbca(M1 CodeKB 머지 반영, 충돌 없음 — F68=src/agent only, CodeKB=codekb/룰파일), verify green (978 passed), --no-ff merged -->
- **Branch**: feat/F68
- **Worktree**: .claude/worktrees/F68
- **Submodule branch**: — (monorepo; parent-repo Python only)
- **Base commit**: 58ca6a7 (post-F63 머지 main)
- **Start Date**: 2026-06-06

## Extension Configuration
- **Security Baseline**: Enabled — N/A 위주 (내부 에이전트 로직 정리, 시크릿/IaC/auth 무관).
- **Property-Based Testing**: 기존 PBT 유지. is_meaningful 제거 시 관련 PBT도 정리.

## Scope
F67 code-review에서 latent/cleanup으로 분류된 3건. 관련: [[f64-f65-self-learning-design]].

- **#7 rollback-rewrite 순서** (`orchestrator._run_self_rewrite`): `maybe_rollback()`이 current_version을 부모로 되돌린 뒤 `propose_rewrite()`가 롤백 전 버전의 cur/sample로 게이트 판정 → 한 EOD에 rollback+rewrite가 같이 발화하면 자기 자신과 싸움. **결정: 롤백 발생 시 같은 EOD rewrite 건너뛰기**(finding 권고). `_rewrite_fn=None`이라 현재 inert지만 배선 대비 선반영.
- **#8 collect_outcomes EOD 2회 호출** (efficiency): `_run_self_rewrite`가 `_lesson_efficacy` 캐시를 우회해 collect_outcomes(yfinance 전체 fetch)를 두 번째로 실행. **결정(UAQ): outcomes까지 캐시** — `_efficacy_cached` 튜플을 `(day, outcomes, efficacy)`로 확장해 두 경로가 공유.
- **#10 is_meaningful/persists dead code** (efficacy.py): 프로덕션 콜러 0(단위테스트만) + recall/self_rewrite가 동일 임계 3곳 인라인 재구현 + default min_effect=0.0 무력 게이트. **결정(UAQ): 제거** — is_meaningful/persists + 단위테스트 삭제, 인라인 임계를 상수로 추출해 drift 방지.

## Merge Risk Notes
- **공유 파일**: `src/agent/orchestrator.py`, `src/agent/efficacy.py`, `src/agent/recall.py`, `src/agent/self_rewrite.py`, `tests/test_efficacy.py`, `tests/test_recall.py` — 자가학습 스택(F62/F65/F67)이 방금 머지된 직후라 동일 영역.
- **API/시그니처 변경**: `efficacy.is_meaningful`/`persists` 삭제(외부 콜러 없음 확인됨), `orchestrator._efficacy_cached` 튜플 형태 변경(내부), `_run_self_rewrite` 롤백 가드 추가.
- **알려진 동시 변경**: 없음(현재 다른 active 트랙은 자가학습 영역 미접촉으로 추정 — 머지 시 재확인).

## Stage Progress
- [x] Workspace Detection — reused (brownfield)
- [x] Requirements Analysis — minimal (F67 follow-up 3건, #7 기계수정 + #8/#10 UAQ 결정)
- [x] User Stories — SKIP (내부 정리)
- [x] Workflow Planning — SKIP (단일 cleanup 트랙)
- [x] Construction — #7 + #8 + #10 수정 (커밋 aeb47bd)
  - #10: is_meaningful/persists 삭제 + MIN_EFFICACY_SAMPLE=20 상수 단일화(recall/self_rewrite 참조) + 단위테스트 제거
  - #8: `_efficacy_cached`를 (day, outcomes)로 확장 + `_cached_outcomes()` 헬퍼 → _lesson_efficacy/_run_self_rewrite 공유(collect_outcomes 1회/일)
  - #7: 롤백 발생 시 같은 EOD rewrite 건너뛰기 + cur/sample을 롤백 후 읽기
- [x] Build & Test — **978 passed**. py_compile 클린. 신규 tests/test_orchestrator_selflearning.py(4). is_meaningful/persists 외부 콜러 0 확인.
- **Status**: merge-awaiting → `/ai-dlc-merge`

# F102 — Toss 요율 자동 갱신과 독립 가상 운용

**Status**: merge-awaiting
**Branch**: feat/F102
**Base**: 3a407b6
**Workspace**: .claude/worktrees/F102
**Updated**: 2026-11-23

## Scope / authorization

사용자 요청에 따라 만료 요율 재조회와 Toss 기준 dry 평가를 로컬 구현한다.
기존 자율 진행 지시에 따라 단계별 재승인은 생략한다. 실계좌 주문, Alpaca 계좌 변경,
기존 데몬 재시작, 원격 push는 포함하지 않는다. 연간 양도소득세는 별도 처리한다.

## Stage Progress

- [x] Workspace detection / targeted reverse engineering: 기존 Toss adapter, agent executor,
  simulator, 계좌 CLI 확인. CodeKB SHA 4f3fcbf는 오래되어 실제 코드로 보완; CodeKB 수정 없음.
- [x] Requirements / stories / design / plan: inception/plan.md
- [x] Code generation
- [x] Build and test / read-only smoke / review: 1806 passed, 30 기존 경고; Ruff/diff check 통과.
- [x] Post-merge guide
- [ ] Local integration

## Extension Configuration

Security baseline / property-based testing: Disabled (기존 미선택 상태 유지).
금융 장부, 재시작 일관성, GET-only 경계의 구체적 회귀 테스트는 기본 검증에 포함한다.

## Merge Risk Notes

factory, config, account CLI를 공유한다. 기존 브로커 기본값은 유지한다.
F73/F98/F99 worktree는 수정하지 않는다. 병합 직전 main 변경을 재확인한다.
main은 base 3a407b6 이후 변경 없고 clean임을 확인했다. 기존 운영 프로세스 변경 없음.

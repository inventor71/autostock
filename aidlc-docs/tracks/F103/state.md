# F103 — 매도·보호 의도 보존과 Toss 호가 품질

**Status**: merge-awaiting
**Branch**: feat/F103
**Base**: 79c756d
**Workspace**: .claude/worktrees/F103
**Updated**: 2026-11-24

## Scope / authorization

F102의 실운용 후속 수정. 사용자가 두 문제의 개선과 완료 후 Opus/Fable dry tmux 재실행을 요청했다.
기존 자율 진행 지시로 단계별 재승인은 생략한다. 로컬 병합과 dry 프로세스 재시작까지 수행한다.
실계좌 주문, 다른 데몬 재시작, 원격 push는 제외한다. 기존 장부·종료 기한·모델 설정을 유지한다.

## Stage Progress

- [x] Workspace detection / targeted reverse engineering: executor, shadow broker, runner와 실제 11/23 기록 확인.
- [x] Requirements / workflow / functional design: inception/plan.md
- [x] Code generation
- [x] Build and test / replay review: 최종 전체 1,824 passed, 관련 suite 70 passed, 신규 Ruff 진단 0.
- [ ] Local merge / dry restart / post-merge verification

## Extension Configuration

Security baseline / property-based testing: Disabled — F102 선택 유지.
금융 수량 보존, 지연 체결, 재시작, stale quote 경계의 회귀 검증은 기본 범위다.

## Merge Risk Notes

공유 executor 변경은 Alpaca/Simulated에도 영향을 주므로 전체 Python 회귀 테스트가 필요하다.
계좌 장부 v1은 읽기 호환을 유지하고 새 품질 통계는 적용 이후부터 별도로 집계한다.
CodeKB 4f3fcbf는 오래되어 실제 코드로 보완했으며 CI 소유 문서는 수정하지 않는다.
F73/F98/F99 worktree는 수정하지 않는다.
Pre-merge 재점검: main은 base 79c756d 그대로이며 추가 공유 코드 변경/충돌이 없다.

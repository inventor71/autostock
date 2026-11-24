# F104 — Toss 소수점 매도 수량과 반복 재시도 수정

**Status**: merge-awaiting
**Branch**: feat/F104
**Base**: 79dc948
**Workspace**: .claude/worktrees/F104
**Updated**: 2026-11-24

## Scope / authorization

F103 운영 후속: 사용자가 두 dry run의 반복 오류 원인을 요청했다. 기존 로컬 개선·재시작
권한으로 원인 수정과 두 dry runner 적용까지 수행한다. 실제 주문이나 원격 push는 하지 않는다.
정밀도가 다른 Alpaca 공통 RiskManager는 유지하고 Toss 시장가 부분 매도의 경계에서 수량을 내린다.
모델·장부·유효한 결정은 유지하며 지연된 결정은 적용 시점의 새 호가로만 가상 체결한다.

## Plan

- [x] 양쪽 tmux/장부 관측: 9자리 RiskManager 수량과 Toss 6자리 제약 충돌, 관찰마다 재시도.
- [x] Toss 시장가 매도 수량을 Decimal 기준 6자리로 내림; 최소 단위 미만/비정상 입력 거부.
- [x] shadow 결정별 오류의 영속적 재시도 간격과 보고, 정상 부분 체결 후 보호는 지연 없이 유지.
- [x] 실제 소수점 잔고·매도 비율, 부분 체결/재시작/수량 보존, 재시도/만료 경계 테스트: 전체 1,834 passed.
- [ ] 로컬 병합, private 백업, 양쪽 dry 재시작, pending 매도와 후속 보호의 실제 가상 체결 확인.

## Extension Configuration

Security baseline / PBT: Disabled — F103 선택 유지. 정밀도·중복·재시작 회귀 검증은 기본 범위.

## Merge Risk Notes

Toss 어댑터의 수량 처리와 shadow executor만 변경한다. F73/F98/F99와 일반 데몬은 건드리지 않는다.
에이전트 호출 없이 관찰 루프가 미처리 결정을 재개하므로, 과거 기록 보존과 적용 이후 체결 시점을
명확히 구분한다. 기존 커서를 되감거나 과거 호가로 소급 체결하지 않는다.
Pre-merge 점검: main은 base 79dc948 그대로이며 추가 공유 변경이 없다.

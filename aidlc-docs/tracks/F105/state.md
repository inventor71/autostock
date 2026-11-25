# F105 — 정상·dry 모드의 장중 정보 갱신과 데이터 품질

**Status**: merge-awaiting
**Branch**: feat/F105
**Base**: d818e6c
**Workspace**: .claude/worktrees/F105
**Updated**: 2026-11-25

## Scope / authorization

사용자: “개선을 정상/dry 모드에 적용해줘”. 직전 Nov24 trace 조사에서 확인한
도구 설정 오류, 뉴스 실패의 빈 결과 위장, 장중 정보 누락과 기준 시각 불명확성을 수정한다.
기존 로컬 수정·두 dry 재시작 권한을 유지한다. 실제 주문, 계좌 변경, 원격 push는 제외한다.
정상·dry 공통 경로를 사용하며 모델, 위험 한도, no-trade 원칙과 기존 dry 장부를 보존한다.

## Plan

- [x] Workspace / 요구사항: 기존 Python 앱, CodeKB를 참고하고 현재 관련 소스를 직접 확인.
- [x] 설계: configured universe와 뉴스 provider 공통 사용, 실패/미조회/정상 빈 결과 구분.
- [x] 도구 수정: 시그널 CLI universe, 실행 시 뉴스 fallback, 가격·지표·매크로 원천 시각.
- [x] 장중 공통 브리프: held/watch/시장 지표, 최신 뉴스와 coverage를 정상·dry에 전달.
- [x] 프롬프트: 미확인을 변화 없음으로 취급하지 않고 판단에 필요한 부분만 추가 확인.
- [x] 회귀 검증: 실제 설정 스키마→CLI, provider 실패/복구, 장중 소식 전달, 장부 보존.
- [x] 전체 Python 테스트 1,860 passed / Ruff 신규 진단 0 / 실제 read-only 데이터 점검.
- [ ] 로컬 병합 / dry 두 실행 적용과 상태 확인.

단일 연계 수정으로 기존 컴포넌트 안에서 구현한다. 별도 사용자 스토리·인프라 구축은 생략.
외부 조회는 기존 timeout/cache 정책을 사용하고 모델 호출 빈도를 자동 증가시키지 않는다.
수익률 개선의 증명은 미래 dry 결과로 별도 평가한다.

## Extension Configuration

Security baseline / PBT: Disabled — F103/F104의 기존 선택 유지. 실패 경계와 실제 연결의
결정적 회귀 테스트는 기본 검증 범위에 포함한다.

## Merge Risk Notes

agent intraday, signals collector, market tools, news providers, Toss shadow가 공유 변경 대상.
F73/F98/F99의 미병합 작업은 수정하지 않는다. merge 전 main 신규 변경을 재확인한다.
뉴스 오류는 기존 list 소비자에서도 오류로 관측되게 하고 fallback/brief 경계에서 흡수한다.

main은 d818e6c 그대로이며 이 트랙 작업 중 추가 병합이 없다. 새 뉴스/가격 metadata는
기존 JSON 키를 유지하는 추가형 변경이다. macro 최상위 as_of는 None이며 실제 시각은
각 시계열 source_as_of, 수집 시각은 retrieved_at으로 구분한다. NewsPoller.diff_for는
이제 전달 시 unread를 소비한다. 예약 턴이 실제 수락된 후에만 브리프를 만든다.

검증 및 실제 데이터 한계는 [verification.md](verification.md), 운영 방법은
[post-merge-guide.md](post-merge-guide.md)를 참고한다.

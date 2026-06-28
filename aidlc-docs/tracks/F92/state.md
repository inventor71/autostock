# Track F92 — 브로커 provider 정합성 버그 수정 + 멀티 인스턴스 격리 복구

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F92
- **Title**: 브로커 provider 정합성 버그 수정 + 멀티 인스턴스 격리 복구
- **Type**: feature (bugfix + refactor + ops surgery)
- **Status**: merged → main 8181f5c (2026-06-28)
- **Branch**: feat/F92
- **Worktree**: .claude/worktrees/F92
- **Submodule branch**: — (parent repo only; operator-console 미변경 예상)
- **Base commit**: 42d0398
- **Start Date**: 2026-06-28

## Extension Configuration
- **Security Baseline**: Disabled (사용자 opt-out 2026-06-28; 내부 정합성 버그, 신규 공격면 없음)
- **Property-Based Testing**: Disabled (사용자 opt-out 2026-06-28; 팩토리 배선/조사/surgery 중심, PBT 적합 로직 적음)

## Surgery 방식 (사용자 결정 2026-06-28)
- **리셋 + reconcile**: 각 인스턴스 workspace 거래상태 파일 비우고 데몬이 실 sub-account
  truth로 재구축. 실보유 HD/HON/GILD 포지션은 유지(청산 안 함).

## Scope
운영 중인 Docker prod 3개 인스턴스(aggressive/balanced/conservative)에서 발견된 **브로커
provider 정합성 버그**를 수정한다. 데몬 주문실행은 `main.py::create_broker()`(provider-aware)로
올바른 account_farm sub-account에 격리되어 있으나, agent가 broker-truth(손익/포지션/주문)를
읽는 CLI 경로 2곳이 provider를 무시하고 `AlpacaBroker`를 하드코딩 → 3 인스턴스가 공유 Alpaca
페이퍼 계좌 하나를 읽는다. 결과적으로 agent가 **자기 실계좌 보유분을 못 보고** 유령 포지션
(pre-docker RTX/TMO)에 대해 의사결정해 왔다.

영향 지점(확인됨):
- `src/agent/tools/__main__.py::_broker()` — `python -m src.agent.tools account`, 시그널 held-lookup
- `src/agent/logs/equity.py::main()` — `python -m src.agent.logs.equity` (equity.jsonl 기록)

목표:
1. 두 우회 경로를 `create_broker()` 경유로 통일. `create_broker`를 공유 팩토리 모듈로 추출
   (monorepo-native — 원래 그 구조였던 듯 읽히게). [[feedback-monorepo-refactor-as-native]]
2. 격리 전수 점검 — 공유되면 안 되는데 공유되는 다른 지점(하드코딩 브로커/`settings.alpaca_*`
   직접참조/데이터 프로바이더/캐시/계좌별로 갈라져야 하는 상태) 조사·수정.
3. 운영 컨테이너 surgery — 영향 파일/워크스페이스를 "원래 독립 실행이었을 때" 기준으로 정리.
4. 회귀 방지 테스트.

라이브 확인된 실제 sub-account 보유:
- aggressive (8eec): HD 4 @342.61, equity 79,651
- balanced (75aa): HON 9 @228.84, equity 75,928
- conservative (6ddc): GILD 14 @126.47, equity 51,254
- 셋 다 RTX/TMO 미보유 (RTX/TMO는 공유 Alpaca 계좌의 유령 데이터)

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성.

- **공유 파일 (주의)**: `main.py` (create_broker 추출 시), `src/agent/tools/__main__.py`,
  `src/agent/logs/equity.py`, 신규 `src/execution/brokers/factory.py`
- **API/시그니처 변경**: `create_broker` 위치 이동(main.py → factory 모듈); main.py는 re-export
  또는 import 경유로 호환 유지 검토
- **알려진 동시 변경**: 없음 (확인 필요)

## Stage Progress
- [x] Workspace Detection
- [x] Requirements Analysis — standard
- [x] User Stories — skip (내부 정합성 버그, 사용자 워크플로 신규 없음)
- [x] Workflow Planning
- [x] Application Design — skip (신규 컴포넌트 없음; 기존 팩토리 추출/재배선)
- [x] Units Generation — skip (단일 단위)
- [x] Construction (per-unit Code Generation)
  - [x] Unit-1 broker factory 통일 + 격리 점검 + surgery 헬퍼 (코드+테스트 green)
- [x] Build & Test (F92 변경분 green; post-merge-guide.md + reconcile 헬퍼)

# Track F70 — 섀도우 벤치마크 + alpha-vs-baseline 비교 (결정론적 전략을 측정자로 상시 가동)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F70
- **Title**: 섀도우 벤치마크 + alpha-vs-baseline 비교 — 결정론적 전략(기술적/buy&hold)을 LLM 경쟁자가 아닌 측정자로 상시 가동
- **Type**: feature
- **Status**: merge-awaiting  <!-- Build & Test green 2026-06-07; /ai-dlc-merge가 merged로 전환 -->
- **Branch**: feat/F70
- **Worktree**: .claude/worktrees/F70
- **Submodule branch**: — (operator-console/cli 미변경 — Python/config만)
- **Base commit**: 5e5c2a9 (worktree 분기 시점)
- **Start Date**: 2026-06-07T02:40:49Z

## Extension Configuration
- **Security Baseline**: **Enabled (범위 한정)** — 적용: sandbox 계정 자격증명/account_id fail-closed,
  스냅샷 시크릿 미포함(account_masked만, `BrokerApiBroker._mask` 준수). N/A: 인증/인가 흐름,
  외부 노출 엔드포인트(내부 측정·로컬 파일). 검증: `test_store.py::test_record_never_persists_raw_secret`.
- **Property-Based Testing**: **Enabled (Partial)** — 순수 함수(`metrics.compute_metrics`)에 hypothesis
  PBT(동일입력=동일출력, MDD≤0). 부수효과 경로(브로커 I/O)는 fake 단위테스트로 커버.

## Scope
LLM 단독(`active_strategies: [llm]`)으로 운영되는 현 라이브 경로에서 고아 상태인 결정론적 전략
(기술적 MA/RSI/MACD/Bollinger, ML, 그리고 buy-and-hold)을 **경쟁/앙상블이 아닌 벤치마크(측정자)**
로 재배치한다. 핵심 질문: "LLM이 비용·리스크를 감수할 만큼 단순 baseline을 실제로 이기는가?"

방향(요구사항 게이트에서 확정 예정):
- 동일 forward 구간에서 baseline 섀도우 포트폴리오의 페이퍼 equity 곡선을 상시 산출
- LLM 라이브 페이퍼 성과 vs baseline → alpha-vs-baseline 지표
- 백테스트 엔진의 역할을 "결정론적 전략 튜닝/리그레션"으로 명확히 한정 (LLM에는 미적용 — 룩어헤드/비재현/비용)

관련: [[llm-trader-redesign]], [[risk-execution-redesign]], 직전 토론(섀도우 벤치마크 권고).

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성. `/ai-dlc-merge`가 큐 구성·충돌 해결 시 참조.
> 비워두면 `/ai-dlc-merge`가 `git diff --name-only`로 자동 추론.

- **공유 파일 (주의)**: `main.py`(run_agent에 벤치마크 start/stop 훅 + `_build_risk_manager`/
  `_maybe_start_benchmark` 헬퍼 추가) — **데몬 경로**라 F69(Health TUI)·F33(멀티브로커) 등 동시
  데몬 작업과 겹칠 수 있음. `config/config.py`(Settings에 `benchmark` 필드 1줄), `config/settings.yaml`,
  `config/strategies.yaml`(buy_and_hold 추가), `.gitignore`.
- **API/시그니처 변경**: 없음(추가형). `src/strategy/registry.py` 미변경. `broker_api_broker.py`
  재사용만(R3 머지된 Alpaca-shaped base 위에서 동작 — rebase 시 import 경로 확인).
- **알려진 동시 변경**: `main.py` run_agent — F69/F33이 같은 함수를 건드리면 수동 머지 필요.
  신규 `src/benchmark/`·`tests/benchmark/`·`src/strategy/buy_and_hold.py`는 충돌 위험 거의 없음.

## Stage Progress
- [x] Workspace Detection — brownfield, codekb 존재, 재개 아님(신규)
- [x] Requirements Analysis — standard ✅ 승인 (baseline 5개, ML 제외, 전용 dir 저장)
- [x] User Stories — SKIP (내부 측정 인프라/데이터 스토어, 사용자 워크플로 없음 — 단일 페르소나=개발자)
- [x] Workflow Planning ✅ 승인
- [x] Application Design — EXECUTE ✅ 승인 (C1~C6 컴포넌트 모델)
- [x] Units Generation — SKIP (단일 응집 유닛 `benchmark`)
- [x] Construction (per-unit Code Generation)
  - [x] benchmark — buy&hold 전략 + config/store/metrics/runner + main 와이어링 + 테스트
- [x] Build & Test — `pytest tests/benchmark` 30 passed, 인접 회귀 35 passed, CLI E2E, toggle-off 무영향

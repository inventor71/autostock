# Track F96 — 진입 실행 가드(decision→fill 드리프트) + 뉴스 신선도/priced-in

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F96
- **Title**: 진입 실행 가드(decision→fill 드리프트) + 뉴스 신선도/priced-in 할인
- **Type**: feature
- **Status**: merged → main 6211cfc (2026-07-17)
- **Branch**: feat/F96
- **Worktree**: .claude/worktrees/F96
- **Submodule branch**: — (monorepo; Python 전용, operator-console 미변경 예상)
- **Base commit**: 4f3fcbf
- **Start Date**: 2026-07-07T14:37:59Z

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | No | Requirements Analysis |
| Property-Based Testing | No | Requirements Analysis |

> 사용자 UAQ opt-in "둘 다 미적용". 내부 실행 로직 + 기존 news provider 재사용 → 신규 외부 입력/공격
> 표면 없음(Security Baseline N/A). 드리프트 판정·age 계산은 순수 함수라 예제 기반 단위테스트로 충분(PBT 미적용).

## Scope
실행 계층 두 가지 개선을 한 트랙으로 진행한다.

- **(#4) Execution guard** — `DecisionExecutor.execute_decision`에서, 결정 기준가 대비
  실행 시점 현재가의 **역방향 드리프트**가 임계를 초과하면 나쁜 체결을 막는다.
  근본 원인: 모멘텀 진입(entry ≥ 현재가)이 현재 MARKET 주문으로 나가
  (`src/risk/manager.py:280,291`) decision→fill 가격 드리프트에 무방비.
- **(#3) News freshness / priced-in** — news 툴(`src/agent/tools/market.py:225`)에
  `age_hours` + `priced_in_risk` 플래그를 계산·노출하고, 프롬프트/레슨에
  "24h 초과 촉매 + 고점 근처 진입 = priced-in 할인" 규칙을 추가
  (`src/agent/aggressiveness.py:84` same-week catalyst 선호와 정합).

관련 메모리: [[risk-execution-redesign]] (RiskManager/Broker bracket 설계),
[[llm-trader-redesign]], [[f85-aggressiveness-knob]] (posture 다이얼),
[[f61-market-signals]] (movers/catalyst 시그널).

**범위 제외**: stop floor(#2, 최소 ATR stop 거리), time-lag 튜닝(#1, execute_pending 주기).

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성. `/ai-dlc-merge`가 큐 구성·충돌 해결 시 참조.

- **공유 파일 (주의)**: `src/agent/tools/market.py` (news 툴 수정) — F95(warm-cache 프로듀서)가
  quote 계열 툴을 건드릴 수 있어 겹칠 가능성. `src/agent/prompts.py`(모든 turn 프롬프트).
- **API/시그니처 변경**: TBD (설계 후 기입) — news() 반환 dict에 필드 추가는 additive.
- **알려진 동시 변경**: F95(active, TUI panel + warm-cache), F73(vibeshell, do-not-enqueue),
  F33(paused).

## Stage Progress
- [x] Workspace Detection — brownfield; 관련 코드(executor/risk/market/prompts) 심층 분석 완료
- [x] Requirements Analysis — Standard (UAQ 4문항 확정: LIMIT강등·0.5ATR·조언용·확장미적용)
- [ ] User Stories — SKIP (단일 운영자, 내부 실행 로직; 시나리오는 requirements에 명료)
- [ ] Workflow Planning — 진행 중
- [ ] Application Design — EXECUTE (경량; 배치=RiskManager 확장 확정, 계약 명시)
- [ ] Units Generation — SKIP (단일 소규모 단위 2건 독립; 별도 분해 불필요)
- [x] Construction (per-unit Code Generation)
  - [x] U1 Execution drift guard — RiskManager anchor(entry∪ref_price) 가드 + ref_price 스탬핑 배선 + config (옵션 B)
  - [x] U2 News freshness — `market.news()` age_hours/priced_in_risk + prompts/aggressiveness 규칙
- [x] Build & Test — 1520 passed / 1 worktree-only 실패(무관, main 통과) + 라이브 스모크 그린

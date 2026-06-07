# Track R7 — Broker behavior fixes (BrokerApiBroker: short-side + fail-closed TIF)

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: R7
- **Title**: BrokerApiBroker behavior fixes deferred from R3 (short-side mapping bug + TIF policy)
- **Type**: refactor (behavior change — NOT behavior-preserving)
- **Status**: merge-awaiting  <!-- R3 landed (cfd34b0); R7 implemented + green 2026-06-07 -->
- **Branch**: refactor/R7
- **Worktree**: .claude/worktrees/R7
- **Submodule branch**: — (Python only)
- **Base commit**: c9669ec (worktree 분기; R3 base AlpacaShapedBroker 포함)
- **Start Date**: 2026-06-07
- **Scope note**: T3-3 (extended_hours/client_order_id/trailing 패리티) **제외** — 사용자 결정(2026-06-07), 필요 시 별도 트랙.

## Extension Configuration
- **Security Baseline**: Applicable — **Compliant**. order side/TIF는 trade-affecting. 교정 동작을
  명시 테스트로 고정: BUY_TO_COVER→BUY(short-cover 정확성), SELL_SHORT→SELL, 미지원 side→raise,
  미지원 TIF(opg)→fail-closed raise(조용한 DAY 강등 제거). 숏 게이트([[risk-execution-redesign]],
  F60 ETB)는 RiskManager 레이어라 본 변경(브로커 side 매핑)과 직교 — 영향 없음.
- **Property-Based Testing**: **N/A (rationale)** — side 매핑은 4개 enum + bogus 1개로 입력공간을
  **전수(exhaustive)** 커버, TIF는 day/gtc/ioc/fok/opg/bracket 분기 전수 커버. 생성형 PBT가 추가로
  잡을 입력 공간이 없음(열거가 곧 전수). 따라서 명시 enum 테스트로 충분.

## Scope (carved out of R3's T3 gate — user chose "preserve in R3, fix here")
1. **T3-1 (bug)**: `BrokerApiBroker.submit_order` maps `BUY_TO_COVER→SELL` (wrong; should be BUY)
   and `SELL_SHORT→SELL`. Adopt the shared/correct `_alpaca_side`. **Behavior change** — a short
   *cover* on the sandbox farm currently sends the wrong side. Likely unexercised (farm shorting),
   but it's a real correctness bug.
2. **T3-2 (tightening)**: `BrokerApiBroker._time_in_force` silently downgrades non-GTC→DAY; align
   to the F9 fail-closed policy (reject unsupported TIF) so the two brokers behave the same.
3. **T3-3 (optional)**: extended_hours/client_order_id/trailing-stop parity for broker_api — only
   if `alpaca.broker.requests` accepts those kwargs (needs an SDK check first; may be infeasible).

## Why separate from R3
R3 is a behavior-preserving restructure (pure T1). Folding these behavior changes in would make the
restructure diff impossible to review as "no behavior change". After R3, the shared
`AlpacaShapedBroker` base makes these fixes a few-line change (flip broker_api's overrides to use
the base's correct defaults) + targeted tests.

## Stage Progress — DONE (R3 landed cfd34b0 → unblocked)
- [x] Stage 1 — Baseline + characterization: R3가 이미 틀린 동작을 테스트로 고정해둠
  (`TestPreservedSideMapping`/`TestPreservedTimeInForce`, "R7 flip" 주석 예고)
- [x] Stage 2 — Tier ledger: T3-1/T3-2 = approved-to-change (R3 게이트), T3-3 = 제외(사용자 결정)
- [x] Stage 3 — Redesign: 변경 = 두 subclass override 삭제 → base AlpacaShapedBroker 상속
  (side: BUY_TO_COVER→BUY/raise on unknown; TIF: F9 fail-closed). 신규 동작 = base와 동일.
- [x] Stage 4 — Implementation: `broker_api_broker.py`에서 `_alpaca_side`/`_time_in_force`
  override 삭제 + 미사용 import(Order/OrderClass/OrderSide/AlpacaSide/TimeInForce) 정리.
  테스트 flip: `TestSideMapping`/`TestTimeInForce` (BUY_TO_COVER→BUY, ioc/fok 지원, opg→raise, unknown→raise).
- [x] Build & Test — `tests/test_broker_api_broker.py` 44 passed; 브로커/실행 회귀 190 passed;
  **전체 스위트 1073 passed**; py_compile clean.

## 변경 요약 (behavior change)
- **T3-1 fix**: BrokerApiBroker의 `BUY_TO_COVER` 주문이 이제 올바르게 **BUY**(이전: 잘못 SELL).
  short-cover가 sandbox farm에서 반대 방향으로 나가던 잠재 버그 해소.
- **T3-2 fix**: 미지원 TIF(opg/cls/unknown)를 **조용히 DAY로 강등하지 않고 `BrokerError` raise**
  (AlpacaBroker/F9와 동일 fail-closed). ioc/fok는 이제 정상 지원(이전엔 DAY로 강등됨).
- 두 브로커가 side/TIF에서 **완전히 동일 동작** — R3 추출의 마지막 발산 제거.

See R3's `2-tier-ledger.md` (T3-1/2/3) for the carve-out history.

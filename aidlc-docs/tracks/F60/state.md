# Track F60 — 숏 안전 제어: ETB 게이트 + 마스터 on/off (F54/F59 follow-up)

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F60
- **Title**: Easy-to-borrow 숏 게이트 — 숏 유니버스를 ETB 종목으로 한정 (라이브 브로커 판정)
- **Type**: feature
- **Status**: merged → main b4e41be (2026-06-05)
- **Branch**: feat/F60
- **Worktree**: .claude/worktrees/F60
- **Submodule branch**: — (parent-repo Python only; no opencode change)
- **Base commit**: feat/F59 (41183fd) — **F59 위에 분기** (F59의 `_v_short`도 게이트해야 함)
- **Start Date**: 2026-06-04T00:00:00Z

## Extension Configuration
- **Security Baseline**: Enabled — SECURITY-15 (fail-closed: ETB 확인 불가 시 숏 금지, force로도 우회 불가). SECURITY-03 (no secrets in logs).
- **Property-Based Testing**: Partial — N/A (불리언 게이트, 예제 테스트로 충분).

## Scope
사용자 지적: "빌려서 판다는 게 리스크 — 유동성 종목 아니면 위험하니 easy-to-borrow universe로
한정 필요". 숏 진입을 **ETB(easy-to-borrow) 종목으로만** 허용. 라이브 Alpaca 자산 플래그
(`tradable AND shortable AND easy_to_borrow`)를 진입 전 능동 체크 — Alpaca의 반응형 주문거부를
사전 차단으로 격상. 차입비·리콜/buy-in 리스크 둘 다 ETB로 낮춤. [[risk-execution-redesign]] 연장.

## 의존성 / 머지 순서
- **F59 위에 분기** (base 41183fd). ETB 게이트가 F59의 `_v_short`/`_submit_gated`도 막아야 하므로.
- **머지 순서: F59 → F60.** F59 머지 후 main에 `_v_short`가 생기면 F60은 깨끗이 rebase됨.
  F59 미머지 상태로 F60만 머지하면 F59 커밋이 딸려오니, /ai-dlc-merge 큐에서 F59를 먼저(또는 함께) 처리.

## Merge Risk Notes
- **공유 파일**: `src/execution/base.py`, `src/execution/brokers/alpaca_broker.py`,
  `src/agent/executor.py`, `src/agent/steering/commands.py`, `src/agent/prompts.py` — F54/F59와 동일 영역.
- **API 추가**: `BaseBroker.is_shortable(symbol)` (default True; Alpaca override). 추가만, 기존 시그니처 불변.
- **알려진 동시 변경**: F59(같은 commands.py `_submit_gated`/`_v_short`) — F60이 F59 위에 분기하여 해소.

## Stage Progress
- [x] Workspace Detection — reused (brownfield)
- [x] Requirements — minimal (사용자 확정: 라이브 브로커 ETB 체크 / 새 트랙 F60)
- [x] User Stories — SKIP (안전 게이트, 운영 패턴 확장)
- [x] Workflow Planning — single unit, Functional Design folded
- [x] Construction (Code Generation) — COMPLETE 2026-06-04
  - `BaseBroker.is_shortable` (default True) + `AlpacaBroker.is_shortable` (tradable∧shortable∧easy_to_borrow, 30min 캐시, fail-closed False)
  - executor: SELL_SHORT 진입 전 게이트 (auto-flip 이전 — 비-ETB는 롱 청산도 안 함), `skipped_not_shortable` terminal
  - commands `_submit_gated`: SELL_SHORT ETB 게이트 (/short + place_order 공통, force 비우회)
  - prompts `_SHORT_GUIDANCE`: ETB 한정 안내 (에이전트 결정 낭비 방지)
- [x] Build & Test — PASSED 2026-06-04
  - Python full suite 801 green (+7 ETB tests); buy/place_order 경로 무영향(77 green)
  - 라이브 read-only: AAPL/TSLA/SPY is_shortable=True 확인; fail-closed False 경로 단위테스트
  - 0 new deps. Status → merge-awaiting.
- [x] /code-review F59+F60 — 6 fixes (commit 991fd81), 2026-06-05
  - #1 BrokerApiBroker.side parity, #2 BrokerApiBroker.is_shortable, #3 SELL-on-SHORT guard,
    #4 transient-cache no-poison, #5 runtime _TRADE_VERBS, #6 TUI verbs/color
  - #7 (ETB gate duplication) deferred — note in Merge Risk
  - +3 tests; full suite 804 green
- [x] Master short on/off toggle (commit 9b597d9), 2026-06-05 — 사용자 요청
  - `risk.shorting_enabled` (배포 기본 **OFF/opt-in**; RiskManager ctor 기본 True, main.py가 config 연결)
  - 단일 소스 RiskManager.shorting_enabled: agent skip / human reject(SHORTING_DISABLED, force 비우회) /
    executor auto-flip 이전 차단(skipped_shorting_disabled terminal) / _submit_gated 사전 차단
  - 기존 숏 커버·손절은 비활성 시에도 작동(포지션 안 가둠)
  - prompts: 비활성 시 숏 가이던스 전부 생략(에이전트 결정 낭비 방지) — orchestrator.shorting_enabled 연결
  - config-only(런타임 verb 없음, 사용자 결정). +6 tests; full suite 810 green

### Build & Test 산출물
- `construction/build-and-test/build-and-test-summary.md`

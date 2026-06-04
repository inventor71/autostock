# Track F54 — Short Selling (숏 포지션)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F54
- **Title**: 숏 포지션 기능 — 시장 균형에 맞춘 숏 매매 + 숏 분석 지원
- **Type**: feature
- **Status**: merge-awaiting  <!-- Build & Test PASSED 2026-06-04 -->
- **Branch**: feat/F54
- **Worktree**: .claude/worktrees/F54
- **Submodule branch**: —
- **Base commit**: 8d09b76 (worktree created 2026-06-04)
- **Start Date**: 2026-06-03T00:00:00Z

## Extension Configuration
- **Security Baseline**: Enabled (enforce, all rules blocking). Applicable: SECURITY-03 (no secrets in logs), SECURITY-11 (risk/auth logic isolated), SECURITY-15 (explicit error handling, fail-closed). N/A: web/DB/IaaS rules.
- **Property-Based Testing**: Partial — Hypothesis. Applicable: pure functions (short stop resolution, bracket validation, P&L sign invariants) and serialization round-trips (Order/Decision models).

## Scope
숏(short selling) 포지션 진입/청산/리스크 관리를 전체 거래 시스템에 추가.
장이 안좋을 때 롱만 유지하는 현재 구조를 개선하여, 시장 균형에 맞춰 숏 포지션도
운영할 수 있도록 하고, 숏을 위한 분석(시그널, 리서치)도 가능하게 함.

## Known Limitations (deferred to follow-up F55+)
- **숏 buying_power 명시 체크 없음** (critic #2): sizing은 per-position `max_position_pct×equity`
  상한 + `max_open_positions` 개수 상한으로 실효 총노출 ≤ ~1x equity. 라이브는 Alpaca 서버측
  마진이 과대 숏을 거부(fail-closed). 명시적 `buying_power`/`shorting_buying_power` 게이트는
  후속 트랙으로 분리(사용자 결정 2026-06-04).
- **equity_log invested/largest가 숏을 gross exposure로 집계** (critic #5): 리포팅 전용,
  트레이딩 로직 무관. gross exposure 의미로는 타당하여 유지(사용자 결정 2026-06-04).

## Merge Risk Notes
> **공유 파일 (주의)**: `src/risk/manager.py`, `src/agent/executor.py`,
> `src/execution/brokers/{alpaca_broker,simulated}.py`, `src/core/{types,models}.py` —
> 다른 활성 트랙(F51 장초반 시그널)과 겹칠 수 있음.
> **API/시그니처 변경**: `Position`에 `side` 필드 추가(기본 LONG, 하위호환); `ratchet_stop`에
> `position_side` 파라미터 추가(기본 LONG); `Signal`/`OrderSide`/`DecisionAction` enum 확장(추가만).

## Stage Progress

### 🔵 INCEPTION PHASE
- [x] Workspace Detection — Brownfield, complete 2026-06-04
- [x] Reverse Engineering — Focused, complete 2026-06-04
  - Artifacts: `inception/reverse-engineering/short-selling-subsystems.md`
- [x] Requirements Analysis — Standard, approved 2026-06-04
  - Artifacts: `inception/requirements/requirements.md`, `inception/requirements/requirement-verification-questions.md`
  - Q1=C, Q2=A, Q3=C, Q4=B, Q5=B, Q6=C, Q7=A, Q8=D, Q9=A, Q10=A, Q11=B
- [x] User Stories — SKIP (단일 운영자, 프로젝트 패턴)
- [x] Workflow Planning — Approved 2026-06-04
  - Artifacts: `inception/plans/execution-plan.md`
  - 2 Units: A (Trading Core), B (Agent Intelligence)
- [x] Application Design — SKIP (기존 패키지 내 확장, Functional Design으로 충분)
- [x] Units Generation — COMPLETED 2026-06-04
  - Artifacts: `inception/units/unit-of-work.md`

### 🟢 CONSTRUCTION PHASE — Unit A: Trading Core
- [x] Functional Design — APPROVED 2026-06-04
  - Artifacts: `construction/unit-a-trading-core/functional-design/{domain-entities,business-logic-model,business-rules}.md`
- [x] NFR Requirements — COMPLETED 2026-06-04 (minimal, 0 new deps)
  - Artifacts: `construction/unit-a-trading-core/nfr-requirements/nfr-requirements.md`
- [x] NFR Design — COMPLETED 2026-06-04
  - Artifacts: `construction/unit-a-trading-core/nfr-design/nfr-design-patterns.md`
- [x] Infrastructure Design — SKIP (local daemon, no cloud infra)
- [x] Code Generation — Part 2 COMPLETE 2026-06-04 (commit 245f55a), awaiting approval
  - Artifacts: `construction/plans/unit-a-code-generation-plan.md`
  - Worktree `.claude/worktrees/F54` (branch feat/F54)
  - 36 new tests (incl. Hypothesis PBT); full suite 722 green (686 baseline + 36); 0 new deps
  - All 13 steps done; auto-flip, mandatory-stop, dual breaker, inverted geometry verified

### 🟢 CONSTRUCTION PHASE — Unit B: Agent Intelligence
- [x] Functional Design — APPROVED 2026-06-04
  - Artifacts: `construction/unit-b-agent-intelligence/functional-design/business-logic-model.md`
- [x] NFR Requirements — SKIP (Unit A covers; 0 new deps, read-only tools)
- [x] Infrastructure Design — SKIP
- [x] Code Generation — COMPLETE 2026-06-04 (commit 67848f6)
  - short_data tool, account direction-aware, prompts short guidance, snapshot side,
    place_order side ext, workspace CLAUDE.md
  - 14 new tests; full suite 742 green; 0 new deps
  - Follow-up: opencode TS TUI L/S rendering + /short·/cover surface (data exposed)

### 🟢 CONSTRUCTION PHASE — Final
- [x] Build & Test — PASSED 2026-06-04
  - Artifacts: `construction/build-and-test/` (summary + build/unit/integration/perf)
  - Import smoke OK, pip check clean (0 new deps)
  - Full suite 742 green (56 net-new short tests incl. Hypothesis PBT)
  - Live read-only paper verify PASSED (short_data TSLA, account side field)
  - Status → merge-awaiting

# Track F30 — KIS OpenAPI 브로커 확장

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F30
- **Title**: KIS OpenAPI 브로커 확장 — 한국투자증권 API를 통한 한국주식 페이퍼트레이딩
- **Type**: feature
- **Status**: active
- **Branch**: feat/F30
- **Worktree**: .claude/worktrees/F30
- **Submodule branch**: — (TBD — operator-console/cli 변경 여부 확인 필요)
- **Base commit**: b4fa955
- **Start Date**: 2026-06-01

## Scope
autostock에 한국투자증권(KIS) OpenAPI를 **한국주식 전용** 브로커로 추가하는 **KIS 단독 PoC**:
- 기존 BaseBroker 인터페이스로 KIS OpenAPI 연동
- KOSPI 200 + KOSDAQ 150 종목 페이퍼트레이딩 (Q8=A)
- KIS OpenAPI로 시세 데이터 통합 (Q9=A)
- 공식 SDK git dependency + 래핑 (Q10=A)
- KIS OpenAPI REST 기반 (Linux 호환)
- 실전/모의 환경 분리 (KIS_PAPER_* 환경변수)
- DecisionExecutor: bracket 검증 우회, HOLD/ADJUST_STOP KIS no-op
- TradingScheduler: KST 타임존 파라미터 추가
- 멀티브로커 동시 운영(Alpaca US + KIS KR)은 **F33으로 분리**

Related memories: [[llm-trader-redesign]], [[risk-execution-redesign]], [[worktree-live-verification]]

## Stage Progress
- [x] Workspace Detection
- [x] Requirements Analysis — standard
- [ ] User Stories — skip (내부 인프라 확장, 사용자 페르소나 변화 없음)
- [x] Workflow Planning — standard
- [x] Application Design — execute (KisBroker + KisDataProvider 컴포넌트 설계)
- [ ] Units Generation — skip (단일 컴포넌트, 분해 불필요)
- [ ] Functional Design — execute (주문 유형 매핑 MARKET→01/LIMIT→00, 호가단위 반올림, 정수 수량, 토큰 갱신, universe 정의). 주의: KIS 국내주식 시장가 지원 확인됨 — MARKET→LIMIT 변환 불필요
- [ ] NFR Requirements — execute (rate limiting, 토큰 관리, HTTP timeout, KST 장 시간)
- [ ] Construction — per-unit
  - [ ] Code Generation (KisBroker + KisDataProvider + executor/scheduler 수정 + config)
- [ ] Build & Test

## Extension Configuration
- **Security Baseline**: Enabled — Full (all applicable rules). Applicable: SECURITY-03 (no secrets in logs), SECURITY-05 (input validation), SECURITY-09 (error handling, fail-safe), SECURITY-10 (dependency pinning), SECURITY-11 (secure design, defense in depth), SECURITY-12 (credential management, no hardcoded keys), SECURITY-15 (exception handling, fail-closed). N/A: SECURITY-01, SECURITY-02, SECURITY-04, SECURITY-06, SECURITY-07, SECURITY-08, SECURITY-13, SECURITY-14.
- **Property-Based Testing**: Enabled — Partial mode. Enforced: PBT-02 (round-trip), PBT-03 (invariants), PBT-07 (generator quality), PBT-08 (shrinking/reproducibility), PBT-09 (framework: Hypothesis). N/A (by partial mode): PBT-01, PBT-04, PBT-05, PBT-06, PBT-10.

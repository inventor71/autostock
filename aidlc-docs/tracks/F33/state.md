# Track F33 — 멀티브로커 동시 운영 (Alpaca US + KIS KR)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F33
- **Title**: 멀티브로커 동시 운영 — Alpaca(미국주식) + KIS(한국주식)
- **Type**: feature
- **Status**: active (paused — F30 merge 후 resume)
- **Branch**: feat/F33 (TBD)
- **Worktree**: .claude/worktrees/F33 (TBD)
- **Submodule branch**: —
- **Base commit**: TBD (F30 merge commit)
- **Start Date**: 2026-06-02

## Scope
F30에서 KIS 단독 PoC 완료 후, Alpaca(US) + KIS(KR) 동시 운영을 위한 멀티브로커 아키텍처 구현:

- `AgentTradingMode` 다중 인스턴스 지원 (시장별 독립 인스턴스)
- `TradingScheduler` 다중 타임존 스케줄링 (US Eastern + KST)
- 통합 포트폴리오 콘솔 (Alpaca + KIS 포지션 통합 표시)
- 시장별 RiskManager 모드 (Alpaca=bracket, KIS=legacy)

**Prerequisite**: F30 merged (KIS 단독 운영 안정화)

## Stage Progress
- [ ] Workspace Detection
- [ ] Requirements Analysis — TBD
- [ ] User Stories — TBD
- [ ] Workflow Planning — TBD
- [ ] Application Design — TBD
- [ ] Units Generation — TBD
- [ ] Construction — TBD
- [ ] Build & Test — TBD

## Extension Configuration
- **Security Baseline**: TBD
- **Property-Based Testing**: TBD

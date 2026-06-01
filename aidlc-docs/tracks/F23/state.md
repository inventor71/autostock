# Track F23 — Multi-Agent Research 교차검증 + 시그널 확장

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F23
- **Title**: Multi-Agent Research 교차검증 + 시그널 확장
- **Type**: feature
- **Status**: active
- **Branch**: feat/F23
- **Worktree**: .claude/worktrees/F23
- **Submodule branch**: — (Python-only track)
- **Base commit**: 620eeac
- **Start Date**: 2026-06-01

## Extension Configuration
- **Security Baseline**: TBD (to be confirmed at Requirements Analysis)
- **Property-Based Testing**: TBD (to be confirmed at Requirements Analysis)

## Scope
현재 research agent는 단일 AI 세션(AgentSession → `claude -p`)이 research turn의 판단을 수행함.
이를 N(configurable)개의 agent가 교차검증하는 multi-agent 아키텍처로 개선.
참고 오픈소스: HKUDS AI-Trader, Tauric Research TradingAgents.
추가로 research turn에 참고할 시그널을 확장하고, 모두 settings로 configurable하게 구성.

## Stage Progress
- [x] Workspace Detection — Brownfield, existing project (reverse-engineering artifacts present)
- [x] Requirements Analysis — Standard depth, approved 2026-06-01
- [ ] User Stories — SKIP (내부 agent 아키텍처 변경, 사용자 대면 없음)
- [x] Workflow Planning — approved 2026-06-01
- [ ] Application Design — SKIP (→ Functional Design)
- [ ] Units Generation — SKIP (실행 계획에 정의)
- [ ] Construction (per-unit)
  - [x] Unit 1 `signal-tools` — Code Gen Part 1+2 complete. 30 new tests, 461 total green.
  - [x] Unit 2 `multi-agent-orchestration` — FD + NFR + Code Gen complete. 21 new tests, 482 total green.
- [x] Build & Test — 482 passed, 0 regressions. Import smoke + config OK.

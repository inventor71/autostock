# Track F25 — 타임라인 바 개선 (F22 후속)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F25
- **Title**: 타임라인 바 개선 — market-aware timeline + date nav + human markers
- **Type**: feature
- **Status**: active
- **Branch**: feat/F25
- **Worktree**: .claude/worktrees/F25
- **Submodule branch**: feat/F25 (operator-console/cli)
- **Base commit**: TBD
- **Start Date**: 2026-06-01

## Extension Configuration
- **Security Baseline**: Enabled (enforce, blocking). Applicable: SECURITY-03, SECURITY-11, SECURITY-15. N/A: web/DB/IaC.
- **Property-Based Testing**: Partial (PBT-02/03, Hypothesis + fast-check, pure fn + serialization round-trips)

## Scope
F22 타임라인 바 3가지 개선:
1. Market-aware 시간대: 하드코딩된 US Eastern(9:30-16:00) → config/settings.yaml trading 설정 기반 동적 시간대
2. 24시간 뷰 + 날짜 네비게이션: 하루 24시간 풀뷰, market hours 구간 강조, 이전/다음 날짜 이동
3. Human intervention 마커: steering 명령(human trade, pause, flatten 등)도 타임라인에 마커로 표시

## Stage Progress
- [x] Workspace Detection — Brownfield, existing RE artifacts → skip to Requirements Analysis
- [x] Requirements Analysis — Standard depth, 10 questions + 12h 뷰 후속 결정, APPROVED 2026-06-01
- [x] User Stories — SKIP (단일 운영자 도구, FR로 충분)
- [~] Workflow Planning — 실행 계획 작성 완료, 승인 대기
- [ ] Application Design — SKIP (Functional Design에 흡수)
- [ ] Units Generation — EXECUTE (2 units: A daemon-timeline Python → B timeline-ui TS)
- [~] Construction (per-unit)
  - [~] Unit A (daemon-timeline, Python) — Functional Design 완료, 승인 대기
  - [ ] Unit B (timeline-ui, TypeScript)
- [ ] Build & Test

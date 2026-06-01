# Track F24 — Decision Quality Metrics

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F24
- **Title**: Decision Quality Metrics — 에이전트 결정 품질 정량 분석 프레임워크
- **Type**: feature
- **Status**: merged
- **Branch**: feat/F24
- **Worktree**: .claude/worktrees/F24
- **Submodule branch**: — (parent repo only)
- **Base commit**: 620eeac
- **Start Date**: 2026-06-01

## Extension Configuration
- **Security Baseline**: Enabled — applicable: SECURITY-03 (no secrets in logs), SECURITY-15 (fail-closed). Others N/A (read-only analysis, no web/DB/user-auth).
- **Property-Based Testing**: Enabled — Partial mode (Hypothesis). Apply to pure metric calculation functions.

## Scope
라이브 트랙 레코드(decisions.jsonl + 브로커 히스토리 + 가격 데이터)에서 에이전트 결정 품질을
정량 분석하는 프레임워크. outcome_lines()가 "오늘 이 결정 상태"의 1일짜리 텍스트 스냅샷이라면,
이것은 "N일간 에이전트가 stop을 잘 잡는가, confidence가 보정되어 있는가, 타이밍이 빠른가"를
답하는 통계적 분석 레이어.

**핵심 메트릭:**
- 방향 적중률 (BUY 후 N일 양수? SELL 후 음수?)
- MAE/MFE (Maximum Adverse/Favorable Excursion — 진입 후 최대 역행/순행폭)
- Stop/Target 품질 (noise에 걸렸나 vs 진짜 반전, 도달 시간)
- Confidence 캘리브레이션 (confidence=0.8 결정이 실제 80% 맞나)
- 테제 무효화 속도 (stop 도달 후 인식+행동 지연)
- 실현 R:R (계획 risk:reward vs 실현)
- 벤치마크 대비 초과 성과

**v1 범위 제외 (미래 고려 가능):**
- ~~Monte Carlo permutation test~~ — v1 제외
- ~~Bootstrap CI~~ — v1 제외
- ~~Walk-Forward window analysis~~ — v1 제외

**LLM 호출 없음** — 순수 데이터 분석. 이후 Layer 2 (Paper Tournament)의 기반.

관련 메모리: [[llm-trader-redesign]], [[risk-execution-redesign]], [[project-competitive-positioning]]

## Stage Progress
- [x] Workspace Detection — brownfield, reused
- [x] Requirements Analysis — Standard depth, APPROVED 2026-06-01. Critic: 8 findings reflected.
- [x] User Stories — SKIP (내부 분석 도구, 사용자 대면 기능 없음)
- [x] Workflow Planning — COMPLETE 2026-06-01
- [x] Application Design — SKIP (단일 분석 모듈, Functional Design에 통합)
- [x] Units Generation — SKIP (단일 unit)
- [x] Construction (per-unit Code Generation)
  - [x] `decision-quality-metrics` — FR-1..5, NFR-1..5. 30 tests, 461 total (0 regression).
- [x] Build & Test — 461 passed, 0 new deps, SECURITY-03/15 compliant.

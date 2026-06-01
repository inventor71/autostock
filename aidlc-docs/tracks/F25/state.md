# Track F25 — 타임라인 바 개선 (F22 후속)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F25
- **Title**: 타임라인 바 개선 — market-aware timeline + date nav + human markers
- **Type**: feature
- **Status**: merged
- **Branch**: feat/F25
- **Worktree**: .claude/worktrees/F25
- **Submodule branch**: feat/F25 → merged into submodule main 4c21687
- **Base commit**: 437d57d
- **Merge commit**: (parent) — see registry

## Extension Configuration
- **Security Baseline**: Enabled. SECURITY-03 (intervention 직렬화 시 시크릿 마스킹), SECURITY-15 (시간대/파일 fail-safe).
- **Property-Based Testing**: Partial (Hypothesis Python + bun/fast-check TS), pure fns (et_date, tz, session bounds).

## Scope
F22 타임라인 바 3가지 개선:
1. Market-aware 시간대 (KST 로컬 표시) — daemon이 market 규칙 + tz-aware ts 발행, TS가 IANA tz 변환
2. 12시간 뷰 (정규장 중심) + 날짜 네비게이션 + 3 market 구간 + phase 배지
3. Human intervention 마커 (거래만) + overlay

## Stage Progress
- [x] Workspace Detection — Brownfield, RE artifacts → skip to Requirements Analysis
- [x] Requirements Analysis — Standard, 10Q + 12h 뷰 후속, APPROVED 2026-06-01
- [x] User Stories — SKIP (단일 운영자 도구)
- [x] Workflow Planning — APPROVED (2 units: A daemon-timeline → B timeline-ui)
- [x] Application Design — SKIP (FD에 흡수)
- [x] Units Generation — 2 units 확정
- [x] Construction (per-unit)
  - [x] Unit A (daemon-timeline, Python) — et_date 세션 키, market 규칙 블록, full-ISO ts, interventions(거래만). 556 tests.
  - [x] Unit B (timeline-ui, TypeScript) — 12h market-aware layout(epoch+IANA tz DST), 3구간 배경+라벨+phase 배지,
        날짜 네비(마우스 `< Today >`), human 마커+overlay, flicker-free polling, 마켓 phase 표시. 21 TS tests.
- [x] Build & Test — Python 556 / TS 21 통과, typecheck clean, critic 6건 검토(HIGH 2 + MED 1 반영)
- [x] MERGED — submodule feat/F25 → main 4c21687, parent feat/F25 → main

## 후속 (별도 트랙)
- 키보드(← → T) + `/timeline <date>` slash command — opencode 중앙 keymap 통합 필요 (보류, 마우스 네비로 충족)
- docker root-소유 근본 해결 → **F27** (non-root 컨테이너)

## Worktree
- `.claude/worktrees/F25`, branch `feat/F25`, base 437d57d. 머지 후 정리.
- 서브모듈 git이 docker verify.sh에 의해 수 차례 파괴됨(working tree로 복구) → [[submodule-merge-workflow]], F27이 근본 해결.

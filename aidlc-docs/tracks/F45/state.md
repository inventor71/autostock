# Track F45 — 타임라인 12시간 윈도우 자동 전환 + 12h 네비게이션

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F45
- **Title**: 타임라인 바를 현재시각이 포함된 12h 윈도우로 자동 전환 + [<]/[>] 버튼을 12h 단위 네비로
- **Type**: feature
- **Status**: merged → main 007aa11 (2026-06-03)
- **Branch**: feat/F45 (merged, deleted)
- **Worktree**: — (제거됨)
- **Submodule branch**: — (monorepo, post-F35; operator-console/cli/packages/tui-trading touched)
- **Base commit**: 777cf40
- **Start Date**: 2026-06-03T12:12:37Z

## Extension Configuration
- **Security Baseline**: Disabled — 신규 네트워크/인증/시크릿/입력 표면 없음(순수 로컬 TUI 시간계산). 전 규칙 N/A.
- **Property-Based Testing**: Enabled — 윈도우 선택/타일링/경계 계산이 순수 함수. 속성: (1) ∀now 정확히 한 타일이 now 포함, (2) 인접 타일은 겹침 없이 연속, (3) session 윈도우는 항상 정규장을 포함.

## Scope
타임라인 바(`operator-console/cli/packages/tui-trading/src/components/timeline-bar.tsx`,
`utils/timeline-layout.ts`)의 12h 윈도우 산정 방식을 변경한다.

**문제 (현행 F25 동작)**: `sessionBounds`가 12h 윈도우를 **정규장(regular session) 중심**으로
잡음 (`mid ± 6h`). US 정규장(09:30–16:00 ET)을 KST로 보면 윈도우가 대략 20:00~08:00 KST에
고정됨. 운영자의 현재시각이 이 범위 밖(KST 주간, 예: 10:00/14:00)이면 (a) 타임라인이 현재시각을
포함하지 않고 (b) now-cursor(`nowX`=-1 → ▼/┃ 미표시)도 사라짐.

**목표**: 24시간을 두 개의 12h 윈도우(예: 20:00~08:00, 08:00~20:00)로 나누고, 현재시각이
포함된 윈도우를 **자동 선택**해 now-cursor가 항상 보이게 한다. 날짜 옆 `[ < ]/[ > ]` 버튼은
**12h 단위 윈도우 이동**으로 용도 변경(현행 ±1일 → ±12h). `[ Today ]`는 라이브(현재시각 포함)
윈도우로 복귀.

연관: F25(market-aware timeline 도입), F32(마커 사라짐), F34(라벨 z-order),
F36(과거날짜 마커 조회), F33(멀티브로커 — KR 정규장은 주간 윈도우에 위치). 멀티브로커 맥락에서
주간(08–20 KST)/야간(20–08 KST) 분할은 KR/US 장을 각 절반에 깔끔히 담는 이점이 있음.

## Stage Progress
- [x] Workspace Detection — brownfield, 기존 RE 아티팩트 존재(F25), reverse-eng skip
- [x] Requirements Analysis — standard (Q1=B, Q2=B, Q3=PBT only)
- [x] User Stories — skip (기존 단일 UI 동작 변경, 다중 페르소나 아님)
- [x] Workflow Planning
- [x] Application Design — skip (신규 컴포넌트/서비스 없음; 기존 util/component 내부 변경)
- [x] Units Generation — skip (단일 단위)
- [x] Construction (per-unit Code Generation)
  - [x] tui-trading timeline window — timeline-layout.ts + format.ts + timeline-bar.tsx + tests (61 pass, 0 fail)
- [x] Build & Test — 61 pass 0 fail, typecheck 19 successful

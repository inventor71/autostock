# Track F57 — 상단 status + 날짜 nav 바 두줄 깨짐 + research 경과시간 미갱신 버그 수정

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F57
- **Title**: 상단 status + 날짜 nav 바 두줄 깨짐 + research 경과시간(elapsed) 미갱신 버그 수정
- **Type**: feature (bug fix)
- **Status**: merged → main f53c4a5 (2026-06-04)
- **Branch HEAD**: 7eb6ae7 → merge f53c4a5
- **Branch**: feat/F57
- **Worktree**: .claude/worktrees/F57
- **Submodule branch**: — (monorepo, post-F35; operator-console/cli is in-repo)
- **Base commit**: 6bf1b31
- **Start Date**: 2026-06-03T16:10:30Z

## Extension Configuration
- **Security Baseline**: Enabled — but N/A for this change (pure TUI rendering fix; no
  secrets, auth, risk logic, IO, or error paths touched). No blocking rules apply.
- **Property-Based Testing**: Enabled — N/A. No pure numeric/business functions added;
  fix is JSX layout + Solid reactivity wiring. Existing `fmtTurnLabel` unit tests cover
  the timer format.

## Scope
TUI `TimelineBar` 의 `NavRow`(상단 status + 날짜 네비 동일선, F50 도입) 두 가지 버그:

1. **두줄 깨짐**: status 칩의 내부 `<box>` 가 `flexDirection` 미지정 → opentui 기본
   `column` 으로 `"● "` 와 라벨이 세로로 쌓여 NavRow 가 2줄 높이가 됨. 부모 박스
   `height={3}`(NavRow/TickRow/MarkerRow 3줄) 를 넘쳐 바 전체가 깨져 보임.
   → status `<box>` 에 `flexDirection="row"` 부여.
2. **research 경과시간 미갱신**: `void props.blinkOn` 이 `<Show>` 자식 콜백 본문에서
   1회만 실행되어 `label()`(= `fmtTurnLabel(..., Date.now())`) 의 반응형 추적에서 빠짐.
   500ms blink 틱에 라벨이 재계산되지 않아 `1m12s` 가 멈춤.
   → `void props.blinkOn` 을 `label()` 계산 내부로 이동(TickRow/MarkerRow 의 now-cursor
   blink 와 동일 패턴).

대상 파일: `operator-console/cli/packages/tui-trading/src/components/timeline-bar.tsx`
(`NavRow` 함수만). 관련: F50(동일선 배치), F25/F45(타임라인), F44(in-flight turn 라벨).

## Merge Risk Notes
- **공유 파일 (주의)**: `timeline-bar.tsx` — F55(데이마켓 세션 표기)가 같은 파일의
  MarkerRow/region 로직을 건드릴 가능성. 본 트랙은 `NavRow` 만 수정 → 충돌 표면 최소.
- **API/시그니처 변경**: 없음 (NavRow 내부 JSX/reactivity 만).
- **알려진 동시 변경**: F55 (timeline-bar.tsx), 단 다른 함수 영역.

## Stage Progress
- [x] Workspace Detection — Brownfield, 기존 아티팩트 존재 → Reverse Engineering skip
- [x] Requirements Analysis — minimal (승인 2026-06-03)
- [x] User Stories — skip (내부 UI 버그, 사용자 워크플로 신규 없음)
- [x] Workflow Planning — minimal
- [x] Application Design — skip (신규 컴포넌트/메서드 없음)
- [x] Units Generation — skip (단일 컴포넌트)
- [x] Construction (single unit — NavRow fix) — commit 7eb6ae7
  - [x] NavRow flex-row + blink reactivity 수정
- [x] Build & Test — PASS (8 unit tests, timeline-bar.tsx typecheck clean) → merge-awaiting

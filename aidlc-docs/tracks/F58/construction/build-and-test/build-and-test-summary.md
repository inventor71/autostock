# F58 — Build & Test Summary

단일 단위. 변경 파일 3개 (worktree feat/F58 @ f27c0e5):
- `operator-console/cli/packages/tui-trading/src/utils/format.ts` — `windowedCost` 헬퍼 추가
- `operator-console/cli/packages/tui-trading/src/components/timeline-bar.tsx` — `windowCost`
  memo + NavRow always-show `· $`
- `operator-console/cli/packages/tui-trading/test/window-cost.test.ts` — 신규 단위테스트

## 변경 내용
1. `windowedCost(turns, startMs, endMs)`: `ts ∈ [start, end)` 인 턴의 `cost_usd` 합산.
   파싱불가 ts·범위 밖 제외, `cost_usd || 0` 으로 NaN 안전.
2. `TimelineBar.windowCost` = `windowedCost(session().turns, viewStart(), viewEnd())`.
3. `NavRow`: cost 라벨의 `<Show when={isLive}>` 제거 → 라이브/과거 동일하게 윈도우 합계 표시.
   prop `todayCost`(today_cost_usd) → `windowCost`.

## Build
- 별도 빌드 산출물 없음(소스 TS/TSX). 소비 패키지 `packages/opencode` 번들 경로 포함.

## Unit Test — PASS
```
cd operator-console/cli/packages/tui-trading
bun test test/window-cost.test.ts test/progress-label.test.ts
→ 16 pass / 0 fail
  window-cost(F58): 빈/경계 in·out(start inclusive, end exclusive)/멀티날짜/잘못된 ts/0·NaN cost
  progress-label(F44): 회귀 없음
```

## Typecheck — PASS (changed files)
```
bunx tsgo --noEmit -p packages/tui-trading/tsconfig.json
→ timeline-bar.tsx / format.ts: 오류 0건.
  (hooks/*.ts 의 fs/path 오류는 standalone tsconfig types:[] 선재 격리 아티팩트, 무관.)
```

## 동작 변경 (의도된)
- 라이브 바 cost 가 기존 `today_cost_usd`(ET세션 전체) → **현재 12h 윈도우 합계**로 변경
  (사용자가 윈도우 범위 선택). 라이브 윈도우는 보통 당일 턴 대부분 포함.

## Integration / Live Smoke
- 순수 TUI 렌더 + 저널 읽기. 외부 통합 없음.
- 라이브 육안(머지 후/ docker-verify attach):
  - [ ] `[<]` 로 과거 구간 이동 시 `· $<합계>` 가 그 구간 합으로 표시.
  - [ ] `[<]`/`[>]`/`[Live]` 이동마다 합계 재계산.
  - [ ] 턴 없는 과거 구간은 `· $0.00`.

## 결과: 전 항목 GREEN → 트랙 `merge-awaiting`.

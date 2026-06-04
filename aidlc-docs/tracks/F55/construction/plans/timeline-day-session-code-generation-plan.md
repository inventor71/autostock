# Code Generation Plan — timeline-day-session

작업 위치: worktree `.claude/worktrees/F55` (worktree 게이트 준수, main 코드 변경 금지).

## 구현 체크리스트
- [x] `timeline-layout.ts`: `import { shiftDate } from "../hooks/use-session-data"` (순환참조 없음 확인됨)
- [x] `timeline-layout.ts`: `MarketPhase` 유니온에 `"day"` 추가
- [x] `timeline-layout.ts`: `RegionSpan["kind"]` 유니온에 `"day"` 추가 (`LabelCell["kind"]`는 이를 참조 → 자동)
- [x] `timeline-layout.ts`: `SessionBounds`에 `overnightPrevOpen`/`overnightClose` 추가
- [x] `timeline-layout.ts`: `sessionBounds`가 두 필드 산출 (`shiftDate(±1)` + `etWallToEpoch`)
- [x] `timeline-layout.ts`: `computeLayout.regions`에 day region 2개(prev/curr) push
- [x] `timeline-layout.ts`: `phaseAt`에 두 오버나잇 스팬 분기 추가
- [x] `format.ts`: `PHASE_LABEL.day="DAY-MKT"`, `PHASE_SHORT.day="DAY"`, `PHASE_COLOR.day="#d4b86a"`
- [x] `timeline-bar.tsx`: `REGION_BG.day="#3d3320"`
- [x] 기존 테스트 수정: `regions` 배열 단정 2곳 + phaseAt "classifies"(03:00/21:00 이제 day)
- [x] 신규 테스트: E1~E6 (자정 횡단/DST/phaseAt day/통합 가시성 E4★/롤오버/회귀) — F55 describe 블록
- [x] `bun test` (tui-trading): **77 pass / 0 fail** (timeline-layout.test.ts 51 pass)
- [x] typecheck: F55 변경 파일 0 에러. 잔여 fs/path 에러 4개 파일은 **main과 동일한 pre-existing**
      (패키지 tsconfig `"types": []`로 Node builtin 미해결, F55 무관)

## 회귀 가드
- 기존 off-market 테스트(354-369)는 region 개수 단정 없음 → 통과 유지(단, 이제 day 밴드도 보임).
- 시장 윈도우에서 day 두 스팬 모두 0폭 → 기존 마커/라벨 불변.

# Frontend Components — Timeline "데이마켓"(Overnight) Session

대상: `operator-console/cli/packages/tui-trading` (SolidJS + opentui TUI)

## 변경 표면 (additive)
| 파일 | 변경 |
|---|---|
| `src/utils/timeline-layout.ts` | **(필수)** `MarketPhase`·`RegionSpan["kind"]`·`LabelCell["kind"]` 유니온에 `"day"` 추가; `SessionBounds`에 `overnightPrevOpen`/`overnightClose` 파생 필드 2개; `sessionBounds`가 `shiftDate(±1)`+`etWallToEpoch`로 두 필드 산출; `computeLayout.regions`에 **day region 2개(prev/curr)** push; `phaseAt`에 두 오버나잇 스팬 분기 추가 |
| `src/utils/format.ts` | `PHASE_LABEL.day="DAY-MKT"`, `PHASE_SHORT.day="DAY"`, `PHASE_COLOR.day="#d4b86a"` |
| `src/components/timeline-bar.tsx` | `REGION_BG.day="#3d3320"` 만 추가. MarkerRow 밴드 루프(`260-263`)는 이미 모든 region 순회하므로 **추가 코드 없음**. 경계선 `│`(`265-268`)는 regular 전용 유지 — day는 pre/after처럼 seam 없음. |

> 비고: `MarketRule`(types.ts) 인터페이스는 **변경 없음**(파생 전용). 유니온 타입(`MarketPhase` 등)은
> `timeline-layout.ts`에 정의되어 있어 거기서 확장한다(types.ts 아님). `"day"` 유니온 추가는
> 타입체크/`REGION_BG.day`·`phaseColor("day")` 도달을 위해 **필수**(생략 시 컴파일 에러).

## 상호작용 / 상태
- 새 상태(state) 없음. 기존 `layout` memo 흐름에 region 1개가 추가될 뿐.
- 클릭/hit-test: region 밴드는 클릭 대상이 아님(마커/intervention만). 변경 없음.
- now-cursor / 깜박임 / NavRow nav: 변경 없음.

## 시각 결과 (ASCII 개념도, off-market 12h 윈도우, now=02:00 ET)
```
 20:00      22:00      00:00      02:00      04:00      06:00
 ─DAY──────────────────────────────────────────                  (앰버 밴드 + "DAY" 라벨)
  ^afterClose(D-1)=20:00 ET D-1            ^preOpen(D)=04:00 ET D
```
- pre/after처럼 경계선 `│` 없이 색 밴드 + 인라인 라벨만(regular만 `│` 보유).
- 02:00 ET 라이브 윈도우에선 **prev-day 스팬**(어젯밤 20:00 → 오늘 04:00)이 그려진다(critic 수정 핵심).
- 정규장-중심 윈도우에서는 DAY 밴드 두 스팬 모두 0폭(미표시).
- `[>]`로 다음 off-market 윈도우 이동 시 **curr-day 스팬**(오늘 20:00 → 내일 04:00)이 표시됨.

## API 통합 지점
- 없음(클라이언트 렌더 전용). monitor.json `market` 필드를 읽는 기존 경로 그대로.

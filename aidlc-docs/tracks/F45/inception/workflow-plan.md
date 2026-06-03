# F45 — Workflow Plan + 설계 (Q1=B 정규장-중심 + 보완)

## 실행 단계 결정 (adaptive)
| 단계 | 실행 | 사유 |
|------|------|------|
| Reverse Engineering | skip | brownfield, F25 아티팩트 존재 |
| Requirements Analysis | ✅ done | standard, 질문 3개 답변 완료 |
| User Stories | skip | 단일 TUI 동작 변경, 다중 페르소나/워크플로 아님 |
| Workflow Planning | ✅ (이 문서) | |
| Application Design | skip | 신규 컴포넌트/서비스 없음 |
| Units Generation | skip | 단일 단위(tui-trading) |
| Functional Design | folded-in (아래 §설계) | 윈도우 타일링 로직이 비자명 → 여기 명세 |
| Code Generation | ✅ | §변경 계획 |
| Build & Test | ✅ | bun test (tui-trading) + typecheck |

## 설계 — View 윈도우 모델

핵심: **view 윈도우(x축 투영 범위)** 를 **session bounds(정규장/pre/after instant)** 와 **분리**한다.

- `sessionBounds(etDate, rule)` **변경 없음** → 정규장-중심 12h `[winStart, winEnd]` 제공 (= "장 윈도우").
- 24h는 이 그리드 위에서 정확히 두 종류의 12h 타일로 덮인다:
  - **장 윈도우** = `[winStart, winEnd]` (정규장 포함; KST 야간 ≈ 19:45~07:45).
  - **비장 윈도우** = 그 보완 12h (`[winEnd, winEnd+12h]` 등; KST 주간 ≈ 07:45~19:45, US 폐장).
  - 타일은 정확히 장 윈도우와 그 12h 보완들이므로, 어떤 타일이든 정규장을 **전부 포함**하거나 **전혀 안 겹침**.

### 윈도우 선택/네비
- `liveWindowStart(now, etDate, rule)`: `b=sessionBounds(etDate)`; `k=floor((now-b.winStart)/12h)`;
  `return b.winStart + k*12h`. → 불변식: `start ≤ now < start+12h` (now-cursor 항상 포함 = 버그 수정).
- View 상태: `pinnedStart: number | null` (null = 라이브 추종). `viewStart = pinnedStart ?? liveWindowStart`.
- `[ < ]` → `pinnedStart = viewStart - 12h` · `[ > ]` → `+12h` · `[ Today ]` → `pinnedStart = null`.
- `isLive = pinnedStart == null` (또는 == liveWindowStart). phase 배지/비용은 isLive에서만.

### computeLayout 변경 (back-compat)
- 옵션 인자 `window?: {start:number; end:number}` 추가.
  - 미지정 → view = `[bounds.winStart, bounds.winEnd]` (= 현행 동작; 기존 테스트 그대로 green).
  - 지정 → view = 그 범위. x투영(`xOf`)·ticks·`nowX`는 **view** 기준, regions는 **session bounds**를 view에 clampX.
- 결과: 비장 윈도우에선 regions가 0폭으로 clamp → `r.x1<=r.x0` 가드로 미렌더(US 폐장 빈 밴드). 마커는 instant 기준 배치/엣지 clamp.
- `nowX = now∈[view.start, view.end] ? xOf(now) : -1`.

### 데이터 로딩 (component)
- view 윈도우는 최대 2개 ET date에 걸침(비장 윈도우). `etDateOf(viewStart)`, `etDateOf(viewEnd)`의 **합집합** 세션을 로드·머지
  (라이브 monitor 날짜는 payload, 그 외는 `readHistoricalSession`). regions용 etDate = **윈도우 중점**의 ET date.
- 신규 helper: `etDateOf(ms, tz)` (America/New_York 캘린더 날짜) — `timeline-layout.ts`에 export.

### 라벨 (Q2=B)
- `fmtWindowRange(start, end)` → 로컬 `MM-DD HH:MM → MM-DD HH:MM` (예: `06-04 20:00 → 06-05 08:00`).

## 변경 계획 (Code Generation)
1. `utils/timeline-layout.ts`
   - [ ] `etDateOf(ms, tz)` export 추가.
   - [ ] `liveWindowStart(now, etDate, rule)` + `WINDOW_MS=12h` export 추가.
   - [ ] `computeLayout`에 optional `window` 인자 + view/세션 분리(xOf/ticks/nowX는 view, regions는 clamp).
2. `utils/format.ts`
   - [ ] `fmtWindowRange(start, end)` 추가 (로컬 일시 범위).
3. `components/timeline-bar.tsx`
   - [ ] `pinnedDate`(string) → `pinnedStart`(number|null) 로 교체; `liveWindowStart` 사용.
   - [ ] `goPrev/goNext` = ±12h, `goToday` = null. `selectedWindow()`·`isLive()` 도출.
   - [ ] 세션 데이터: 윈도우가 걸친 ET date들 머지 로드.
   - [ ] `computeLayout({ ..., window: selectedWindow(), etDate: midpointEtDate })`.
   - [ ] `NavRow` 라벨 = `fmtWindowRange(...)`; phase/cost는 isLive 게이트 유지.
4. 테스트 (PBT enabled)
   - [ ] `timeline-layout.test.ts`: `liveWindowStart` 단위 + 속성(∀now 포함/타일 연속/장윈도우⊇정규장), `computeLayout({window})` 비장윈도우 regions 0폭 & nowX 표시, `etDateOf`.
   - [ ] `format` 테스트: `fmtWindowRange`.
   - [ ] 회귀: 기존 timeline-layout/session-data 테스트 green 유지.

## Build & Test
- `cd operator-console/cli/packages/tui-trading && bun test`
- `cd operator-console/cli && bun run typecheck` (tui-trading 범위)

## 불변(보존) 사항
F32 마커 깜박임 수정(단일 text 컴포지션), F34 라벨 z-order, F36 과거 세션 조회 경로, 마커 엣지 clamp(‹/›).

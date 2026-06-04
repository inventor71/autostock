# Business Logic Model — Timeline "데이마켓"(Overnight) Session

## 도메인 개념
- **세션(Session)**: 하루의 거래 구간. 기존 3개(pre/regular/after) + 신규 1개(**day** = 오버나잇).
- **데이마켓(day)**: Alpaca 오버나잇 세션. `[after_close(D), pre_open(D+1)]` = 20:00 ET → 익일 04:00 ET.
  미국 야간 = 한국 낮 → 한국 증권사 브랜딩 "데이마켓".

## ⚠️ 핵심 함정 (critic 검토 반영, F55)
오버나잇 세션은 **ET 자정을 넘어 두 캘린더 날짜에 걸친다**. 그런데 `computeLayout`은 단일
`etDate = primaryEtDate()`(= 뷰 윈도우 중앙의 ET 날짜, `timeline-bar.tsx:54`)만 받는다.
야간(00:00~06:45 ET)에 라이브 오프마켓 윈도우 `[18:45 ET D-1 .. 06:45 ET D]`를 보면 **중앙 날짜는 D**다.
그런데 **지금 화면에 떠야 할 오버나잇 밴드는 어젯밤 개장분 `[20:00 ET D-1, 04:00 ET D]`** (= `afterClose(D-1)→preOpen(D)`).
단일 D 기준으로 `afterClose(D)=20:00 ET D`(미래)만 파생하면 `clampX`가 우측 끝으로 접어 **x1<=x0 → 0폭 → 영영 미표시**,
`phaseAt`도 `closed` 반환 → 배지 오류. ⇒ **반드시 prev-day 오버나잇 스팬을 함께 산출**해야 한다.

## 핵심 로직 (technology-agnostic)

### L1. 세션 경계 파생 (sessionBounds 확장 — 두 스팬)
입력: `etDate`(YYYY-MM-DD, ET), `rule`(MarketRule). `MarketRule` 스키마는 **변경하지 않는다**(파생 전용).
기존 `shiftDate(etDate, n)` 헬퍼(`hooks/use-session-data.ts:224`, 월말/연말 롤오버 검증됨)를 재사용한다.
```
// 신규 SessionBounds 필드 2개 (나머지 두 경계는 기존 preOpen/afterClose 재사용)
overnightPrevOpen = etWallToEpoch(shiftDate(etDate, -1), rule.after_close, tz)  // 20:00 ET (D-1)
overnightClose    = etWallToEpoch(shiftDate(etDate, +1), rule.pre_open,  tz)    // 04:00 ET (D+1)

// 두 오버나잇 스팬:
prevSpan = [overnightPrevOpen, preOpen)   // 어젯밤 개장분: 20:00 D-1 → 04:00 D
currSpan = [afterClose,        overnightClose)  // 오늘밤 개장분: 20:00 D → 04:00 D+1
```
- DST: `etWallToEpoch` 2-pass 보정(`timeline-layout.ts:45-48`)으로 04:00/20:00 wall-time 정확(기존 테스트 통과).
- **`nextEtDate` 인라인 직접 구현 금지** — `shiftDate` 재사용(중복 로직 제거, critic MEDIUM).

### L2. region 산출 (computeLayout — day region 2개 push)
기존 3개 region 배열에 **prev/curr 두 day region**을 추가:
```
{ kind: "day", x0: clampX(overnightPrevOpen), x1: clampX(preOpen) }       // prevSpan
{ kind: "day", x0: clampX(afterClose),        x1: clampX(overnightClose) }// currSpan
```
- view 윈도우 밖 스팬은 `clampX`로 양끝이 같은 edge에 접혀 `x1<=x0` → 기존
  `if(r.x1<=r.x0) continue`(`timeline-bar.tsx:261`) 규약대로 **미표시**. 따라서 어느 윈도우든
  실제로 보이는 한 스팬만 그려진다(시장 윈도우에선 둘 다 0폭).
- 경우별 검증:
  - 시장 윈도우 `[06:45 D, 18:45 D]`: prevSpan 우측 끝<06:45 → 0폭; currSpan 시작 20:00>18:45 → 0폭. (둘 다 미표시 ✓)
  - 오프마켓 `[18:45 D-1, 06:45 D]` (now=02:00 D): prevSpan `[20:00 D-1, 04:00 D]` ⊂ 윈도우 → **표시**; currSpan 미래 → 0폭. ✓
  - 오프마켓 `[18:45 D, 06:45 D+1]` (now=22:00 D, primaryEtDate=D+1): currSpan `[20:00 D, 04:00 D+1]` ⊂ 윈도우 → **표시**; prevSpan `[20:00 D-1,04:00 D]` 좌측 → 0폭. ✓

### L3. 현재 세션 판정 (phaseAt — 두 스팬 모두 검사)
`SessionBounds`에 `overnightPrevOpen`/`overnightClose`가 실리므로 `phaseAt(bounds, ms)`가 두 스팬을 본다.
반열린 구간, 겹침 없음(경계 정각은 다음 세션):
```
regular : [regularOpen, regularClose)
pre     : [preOpen, regularOpen)
after   : [regularClose, afterClose)
day     : [overnightPrevOpen, preOpen)   ∪   [afterClose, overnightClose)   // 신규 (두 구간)
else    : closed
```
- 02:00 ET D (오프마켓 라이브, bounds=D): `[20:00 D-1, 04:00 D)`에 속함 → **"day"** ✓ → 배지 `● DAY-MKT`.
- 04:00 ET D 정각 → prevSpan 미포함(`<preOpen`) → "pre" ✓.
- 21:00 ET D → currSpan `[20:00 D, …)` 포함 → "day" ✓.

## 데이터 흐름
`monitor.market`(MarketRule) → `sessionBounds(etDate, rule)`(+prev/curr 오버나잇) → `computeLayout`
→ `regions[]`(+day×2, 0폭 자동 탈락) → `MarkerRow` 밴드 렌더 + `labelCells`(DAY 라벨, pre/after처럼 boundary `│` 없음)
/ `phaseAt` → NavRow `● DAY-MKT` 배지.

## 엣지 케이스 (테스트 대상 — 통합 테스트 필수)
- **E1 (자정 횡단)**: prevSpan close > open, 차이 ≈ 8h; close가 open의 **다음 캘린더 날짜**.
- **E2 (DST 경계)**: spring-forward/fall-back 날짜에서 overnightPrevOpen(20:00)·overnightClose(04:00) wall-time 정확.
- **E3 (phaseAt)**: bounds=특정 D에서 21:00 D→"day", 02:00 D→"day"(prevSpan), 04:00 D 정각→"pre", 19:59 D→"after".
- **E4 (통합 가시성, ★critic)**: `computeLayout`에 **실제 오프마켓 window**(예: `[18:45 D-1, 06:45 D]`)와
  `etDate=D`를 넘겨 **day region이 폭>0으로 그려지는지** 단정. (hand-bounds phaseAt만으론 이 버그 못 잡음)
- **E5 (월말/연말 롤오버)**: etDate=2026-01-31 → shiftDate(+1)=2026-02-01, shiftDate(-1)=2026-01-30.
- **E6 (회귀)**: 기존 pre/regular/after region 좌표·라벨·regular 경계선 `│`·now-cursor·hit-test 불변.

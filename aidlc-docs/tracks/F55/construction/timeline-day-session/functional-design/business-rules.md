# Business Rules — Timeline "데이마켓"(Overnight) Session

- **BR-1**: 데이마켓(day) 세션 = `[after_close(D), pre_open(D+1)]`. 별도 설정 없이 기존 rule 경계에서 파생한다.
- **BR-1a (★critic, 자정 횡단)**: 단일 etDate 파생은 야간(00:00~06:45 ET)에 라이브 밴드를 누락시킨다.
  `computeLayout`은 **prev-day 스팬 `[afterClose(D-1), preOpen(D)]` 과 curr-day 스팬 `[afterClose(D), preOpen(D+1)]`
  를 모두 산출**하고, view 밖 스팬은 `clampX` 0폭으로 자동 탈락시킨다. `phaseAt`도 두 스팬을 모두 검사한다.
- **BR-1b**: 날짜 증감은 기존 `shiftDate(etDate, n)` 헬퍼를 재사용한다(인라인 재구현 금지).
- **BR-2**: `MarketRule` 스키마와 monitor.json 계약은 변경하지 않는다(파생 전용, 하위호환 보장).
  `SessionBounds`에는 파생 필드 `overnightPrevOpen`/`overnightClose` 2개를 추가한다(내부 타입, 계약 아님).
- **BR-3**: region 경계는 항상 view 윈도우로 clamp하며, 폭이 0이하면 그리지 않는다(기존 규약 유지).
- **BR-4**: DAY 인라인 라벨은 region 폭이 `"DAY".length + 2 = 5` 이상일 때만 표시한다(기존 `labelCells` 규약).
- **BR-4a**: day 밴드는 pre/after와 동일하게 **boundary `│` 글리프를 그리지 않는다**(경계선 `│`는 현재
  코드상 `regular` 전용, `timeline-bar.tsx:265-268`). 색 밴드 + 인라인 라벨만으로 표기 — pre/after와 일관.
- **BR-5**: 라벨 — 짧은 "DAY", 긴(NavRow 배지) "DAY-MKT". 색 — 배경 `#3d3320`, 글자 `#d4b86a`(앰버).
- **BR-6**: `phaseAt`의 구간은 반열린 구간으로 겹치지 않는다. 경계 정각은 다음 세션에 속한다
  (예: 04:00 ET 정각 → "pre", 16:00 정각 → "after", 20:00 정각 → "day").
- **BR-7**: 적용 범위는 Alpaca(미국) 타임라인. `rule.tz`가 무엇이든 로직은 동일하게 동작하지만, 본 트랙은
  미국 rule에만 의미가 있다(KIS는 범위 밖).
- **BR-8 (회귀 금지)**: 기존 pre/regular/after region, 마커/intervention 배치, hit-test, now-cursor,
  F34 라벨 z-order 동작은 변경하지 않는다.

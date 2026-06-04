# F55 요구사항 — 타임라인에 "데이마켓"(Alpaca 오버나잇) 세션 표기 추가

## 1. 의도 분석 (Intent Analysis)
- **User Request (원문)**: "현재 프리/정규/애프터마켓은 타임라인에 표기되나, 데이마켓은 표기안됨"
- **Request Type**: Enhancement (기존 타임라인 기능에 누락된 세션 표기 추가)
- **Scope Estimate**: Single Component (operator-console TUI `tui-trading` 패키지 + 데몬측 MarketRule 발행부)
- **Complexity Estimate**: Moderate — 새 세션이 **ET 자정을 가로지르고(20:00 ET → 익일 04:00 ET)** 기존 region 계산이
  단일 ET 날짜 기준이라, 경계 파생 로직 확장이 필요.
- **Requirements Depth**: Standard

## 2. 용어 확정 (Q&A 결과)
"데이마켓"은 **Alpaca 오버나잇/24시간 세션**을 가리킨다 (Q1=A). 미국 야간장(20:00 ET → 익일 04:00 ET)이
한국 낮시간(≈09:00–17:00 KST)에 열려, 한국 증권사가 이를 "데이마켓"으로 브랜딩한 것과 동일한 구간이다.

| 항목 | 확정값 | 출처 |
|---|---|---|
| 세션 정의 | Alpaca 오버나잇 (애프터마켓 종료 → 익일 프리마켓 시작) | Q1=A |
| 시각/tz | **20:00 ET → 익일 04:00 ET**, `America/New_York` | Q2=A |
| 표기 방식 | 기존 밴드와 동일 — 고유 배경색 + 짧은 라벨 **"DAY"** | Q3=A |
| 적용 범위 | **미국(Alpaca) 타임라인에만** | Q4=A |
| Security 확장 | 미적용 | Q5=B |
| PBT 확장 | 미적용 | Q6=C |

## 3. 현재 동작 (As-Is)
- `MarketRule`(`types.ts` / `_DEFAULT_MARKET_RULE` in `runtime.py`)은 4개 경계만 가진다:
  `pre_open` 04:00 / `regular_open` 09:30 / `regular_close` 16:00 / `after_close` 20:00 (ET).
- `computeLayout`(`timeline-layout.ts`)이 이 경계에서 **3개 region**(`pre`/`regular`/`after`)을 만들고,
  `timeline-bar.tsx`의 `MarkerRow`가 `REGION_BG`(pre=파랑/regular=초록/after=보라) 밴드 + `labelCells`로
  PRE/OPEN/AFT 라벨을 그린다.
- F45: 24시간이 12h 윈도우 2개로 타일링됨. 정규장 중심 윈도우(≈06:45–18:45 ET)에는 PRE/OPEN/AFT가 보이나,
  반대편 12h 윈도우(≈18:45 ET → 익일 06:45 ET)에는 **밴드가 전혀 없다.** 오버나잇 구간(20:00→04:00)이
  바로 이 빈 윈도우에 속한다.

## 4. 기능 요구사항 (Functional Requirements)
- **FR-1**: `MarketRule`에 오버나잇 세션 경계를 표현한다. 새 세션은 `after_close`(20:00 ET, 당일)에서 시작해
  **다음 ET 날짜의 `pre_open`(04:00 ET)** 에서 끝난다 (ET 자정 횡단).
- **FR-2**: `computeLayout`이 4번째 region `kind: "day"`(오버나잇)을 산출한다. 기존 region들과 동일하게
  view 윈도우로 clamp하며, view 밖이면 0폭(`x1<=x0`)으로 그려지지 않는다(기존 `<Show when>` 규약 유지).
- **FR-3**: `MarkerRow`가 `day` region을 고유 배경색 밴드로 그리고, `phaseShort("day")="DAY"`,
  `phaseColor("day")`/`phaseLabel("day")`를 정의해 PRE/OPEN/AFT와 일관된 색·라벨로 표기한다.
  라벨은 폭이 `"DAY".length + 2 = 5` 이상일 때만 표시(기존 `labelCells` 규약 그대로).
- **FR-4**: `phaseAt`이 오버나잇 구간(20:00 ET ≤ t < 익일 04:00 ET)에 대해 `"day"`를 반환해,
  NavRow의 현재-세션 배지(`● DAY`)가 정확히 뜬다. 그 외 시간은 기존대로(`closed` 등).
- **FR-5**: 적용 범위는 Alpaca(미국) 타임라인에 한정한다. KIS/한국장은 본 트랙 범위 밖(향후 F30/F33).

## 5. 비기능 요구사항 (Non-Functional Requirements)
- **NFR-1 (정확성/DST)**: ET 자정 횡단·DST 전환에도 경계가 정확해야 한다. 기존 `etWallToEpoch` 2-pass 보정과
  IANA tz 변환을 재사용한다(새 시간 산식 직접 작성 금지).
- **NFR-2 (시각적 가독성)**: 4번째 밴드 색은 어두운 터미널에서 PRE(파랑)/OPEN(초록)/AFT(보라)와 구분되어야 한다.
- **NFR-3 (회귀 없음)**: 기존 3개 region 렌더링·마커 배치·hit-test·now-cursor·라벨 z-order(F34) 동작 불변.
  기존 `timeline-layout.test.ts` / `timeline-f25` 테스트 전부 통과 유지.
- **NFR-4 (계약 호환)**: `MarketRule` 확장은 하위호환(선택 필드/파생)으로, 구버전 monitor.json도 깨지지 않게.

## 6. 범위 밖 (Out of Scope)
- 한국(KIS) 타임라인 세션 표기 (Q4=A).
- 오버나잇 시간대의 실제 주문 라우팅/체결 로직 변경 (표기 전용).
- 정규장 내부 세분(오전/오후장) 표기 (Q1에서 B 미선택).

## 7. 열린 항목 (Functional Design에서 확정)
- 4번째 region의 정확한 배경색 hex (NFR-2 만족하는 값) 및 `kind` 식별자 최종명(`"day"` 제안).
- 라벨 문자열 최종 확정: **"DAY"**(사용자 용어) 채택 제안 — 다른 운영자에게 야간장임을 오해시킬 여지가 있으면
  `"OVN"` 대안 검토.
- `MarketRule` 확장 형태: 명시적 `overnight_open`/`overnight_close` 필드 추가 vs 기존 경계에서 파생.

## 8. 핵심 요구사항 요약
타임라인에 **Alpaca 오버나잇("데이마켓") 세션(20:00 ET → 익일 04:00 ET)** 을 PRE/OPEN/AFT와 동일한 스타일의
4번째 색 밴드("DAY" 라벨)로 추가한다. ET 자정 횡단을 정확히 처리하고, 미국 타임라인에만 적용하며, 기존 동작은
회귀 없이 보존한다.

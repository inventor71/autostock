# F45 — Requirements Analysis (타임라인 12h 윈도우 자동 전환 + 12h 네비)

**Depth**: Standard (UI 동작 변경, 명확화 질문 필요)
**Type**: Brownfield 기능 변경 (기존 F25 timeline 동작 수정)

## 1. 현행 동작 (As-Is)

- 파일: `operator-console/cli/packages/tui-trading/src/utils/timeline-layout.ts`,
  `src/components/timeline-bar.tsx`.
- `sessionBounds(etDate, rule)` (timeline-layout.ts:56) 가 12h 윈도우를 **정규장 중심**으로 계산:
  `mid = (regularOpen + regularClose)/2`, `winStart = mid - 6h`, `winEnd = mid + 6h`.
  - US 정규장 09:30–16:00 ET → mid ≈ 12:45 ET ≈ 01:45 KST → 윈도우 ≈ **19:45–07:45 KST**
    (사용자 체감 "20:00~08:00"). DST(EST)에는 약 1h 뒤로 이동.
- `nowX` (timeline-layout.ts:217): `now`가 `[winStart, winEnd]` 밖이면 **-1** → TickRow/MarkerRow의
  now-cursor(`▼`/`┃`)가 렌더되지 않음 (timeline-bar.tsx:172, 238).
- 결과: 운영자 현재시각이 KST 주간(예: 10:00, 14:00)이면 (a) 타임라인이 현재시각을 미포함,
  (b) now-cursor 미표시.
- 날짜 네비: `goPrev/goNext` = `shiftDate(±1 day)` (timeline-bar.tsx:49-50,
  use-session-data.ts:224). 라벨 `[ < ] 2026-06-04 (Today) [ > ]`.

## 2. 요구 동작 (To-Be) — 사용자 요청 원문 기반

- **FR-1**: 24시간을 두 개의 12h 윈도우로 분할하고, **현재시각이 포함된 윈도우를 자동 선택**해
  타임라인에 표시한다. → now-cursor가 항상(라이브 뷰에서) 보인다.
- **FR-2**: 날짜 옆 `[ < ]/[ > ]` 버튼의 용도를 **±1일 → ±12h(인접 윈도우)**로 변경한다.
- **FR-3**: `[ Today ]` 버튼은 라이브(현재시각 포함) 윈도우로 복귀한다.
- **FR-4**: 윈도우 라벨은 12h 윈도우(두 날짜에 걸칠 수 있음)를 모호하지 않게 표기한다.
- **FR-5**: 자동 선택된 윈도우에 시장 활동이 없어도(예: US 단독 + KST 주간) 빈 밴드 + 틱 +
  now-cursor를 보여 정상 동작한다.

## 3. 비기능/제약

- 순수 함수(`sessionBounds`/윈도우 선택 로직)는 단위테스트 가능해야 함 (기존 timeline-layout.test.ts 확장).
- DST(EDT/EST) 전환에서 정규장이 한 윈도우 안에 온전히 들어가야 함 (마커/틱이 깨지지 않음).
- 기존 마커 클램핑(offscreen ‹/›), 라벨 z-order(F34), 과거 세션 조회(F36) 동작 보존.
- 멀티브로커(F33) 맥락: 주간(08–20 KST)=KR 장, 야간(20–08 KST)=US 장으로 자연 분리 — 향후 이점.

## 4. 열린 결정 (사용자 질의 — questions.md 참조)

- **Q1 윈도우 분할 기준**: (A) 운영자 로컬시각 08:00/20:00 고정 분할  vs
  (B) 정규장-중심 윈도우 + 그 보완(complement) 12h (DST에 따라 경계가 19:45 등으로 이동).
- **Q2 윈도우 라벨 표기 형식**.
- **Q3 확장(extension) opt-in**: Property-Based Testing / Security Baseline.

## 5. 범위 밖 (Out of scope)

- 두 윈도우(주/야간) **동시** 표시 — 이번엔 한 번에 한 윈도우(현행 단일 바 유지).
- 12h 외 임의 줌/팬, 시간축 스크롤.
- 멀티브로커 신규 구현(F33 별도 트랙).

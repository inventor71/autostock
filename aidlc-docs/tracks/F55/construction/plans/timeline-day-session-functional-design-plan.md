# Functional Design Plan — Timeline "데이마켓"(Overnight) Session

**Unit**: `timeline-day-session`

## 설계 핵심 결정 (Recommended)

### D1. MarketRule 변경 없이 **파생(derive)** 한다 (권장, 위험 최소) — ★critic 반영: 두 스팬
오버나잇 세션은 정의상 **애프터마켓 종료 ~ 다음날 프리마켓 시작** = `[after_close(D), pre_open(D+1)]`.
**새 필드/스키마 변경 없이** `sessionBounds`에서 파생한다.
- ✅ monitor.json 계약 불변 → daemon `runtime.py` **건드리지 않음** (다중 트랙 충돌 위험 제거)
- ✅ 구버전 monitor.json도 그대로 동작 (하위호환 100%)
- ⚠️ **단일 etDate 파생은 야간(00:00~06:45 ET)에 라이브 밴드를 누락**(critic HIGH 확정). →
  `computeLayout`이 **prev/curr 두 오버나잇 스팬을 모두 산출**하고 view 밖은 `clampX` 0폭으로 탈락.
  - `overnightPrevOpen = etWallToEpoch(shiftDate(etDate,-1), after_close, tz)`; prevSpan=`[overnightPrevOpen, preOpen)`
  - `overnightClose    = etWallToEpoch(shiftDate(etDate,+1), pre_open,  tz)`; currSpan=`[afterClose, overnightClose)`
  - `shiftDate`(use-session-data.ts:224) **재사용**(인라인 nextEtDate 금지). DST는 `etWallToEpoch` 2-pass.
- `phaseAt`도 두 스팬을 모두 검사(배지 정확성). 상세는 business-logic-model.md L1~L3 참조.

### D2. region `kind`에 `"day"` 추가
- `RegionSpan["kind"]` / `LabelCell["kind"]` / `MarketPhase` 유니온에 `"day"` 추가.
- `computeLayout`의 `regions`에 4번째 항목 `{ kind: "day", x0: clampX(overnightOpen), x1: clampX(overnightClose) }`.
  `after` 밴드 끝(=afterClose)에서 곧장 이어짐(연속). view 밖이면 기존처럼 0폭 → 미표시.

### D3. `phaseAt`에 오버나잇 분기 추가
- `if (ms >= b.afterClose && ms < b.overnightClose) return "day"` (after 분기 다음).
- NavRow 현재-세션 배지가 야간 시간에 `● DAY`(혹은 확정 라벨)로 표시됨.

### D4. 밴드 색 (NFR-2: 어두운 터미널에서 PRE파랑/OPEN초록/AFT보라와 구분)
- 권장: **앰버/호박색** — `REGION_BG.day = "#3d3320"`, `PHASE_COLOR.day = "#d4b86a"`.
  (파랑/초록/보라와 색상환에서 충분히 떨어짐. 야간=어두운 금색 톤 직관도 부합.)

### D5. 라벨 — **확정 필요** (아래 Question 1)
- `phaseShort.day` = 짧은 3~4글자 라벨, `phaseLabel.day` = NavRow 긴 라벨.

## Plan Checkboxes
- [x] D1 파생 방식 확정 (MarketRule 불변)
- [x] D2 region kind 추가 설계
- [x] D3 phaseAt 분기 설계
- [x] D4 밴드 색 제안
- [x] D5 라벨 문자열 확정 (Q1=A: 짧은 "DAY" / 긴 "DAY-MKT")
- [x] D4 색 확정 (Q2=A: 앰버 #3d3320 / #d4b86a)
- [x] 자정 횡단 / view-window clamp 엣지 케이스 테스트 항목 도출 (artifacts)
- [x] business-logic-model.md / business-rules.md / frontend-components.md 작성

---

## Question 1 — 라벨 문자열
타임라인 밴드의 짧은 라벨과 NavRow 배지의 긴 라벨을 무엇으로 할까요?
(현재: PRE / OPEN / AFT — 짧은 라벨, REGULAR / AFTER-HRS 등 — 긴 라벨)

A) 짧은 **"DAY"** / 긴 **"DAY-MKT"** — 사용자 용어("데이마켓") 그대로. 직관적이나, 야간 구간(20:00~04:00 ET)을
   "DAY"로 부르는 게 다른 사람에겐 낮장으로 오해될 여지 약간 있음.
B) 짧은 **"OVN"** / 긴 **"OVERNIGHT"** — 시간대(야간)에 충실. 의미는 정확하나 사용자 호칭과 다름.
C) 짧은 **"DAY"** / 긴 **"OVERNIGHT"** — 밴드 라벨은 사용자 용어, 배지 설명은 정확한 의미. (절충)
X) 기타 (아래 [Answer]: 뒤에 원하는 짧은/긴 라벨을 직접)

[Answer]: A  → 짧은 "DAY" / 긴 "DAY-MKT" 확정

## Question 2 — 밴드 색
D4의 앰버/호박색(`#3d3320` 배경 / `#d4b86a` 글자) 제안을 채택할까요?

A) 예 — 앰버/호박색 채택
B) 아니오 — 다른 색 원함 (아래에 hex 또는 색 계열 명시)
X) 기타 (아래 [Answer]: 뒤에 설명)

[Answer]: A  → 앰버 채택: REGION_BG.day="#3d3320", PHASE_COLOR.day="#d4b86a"

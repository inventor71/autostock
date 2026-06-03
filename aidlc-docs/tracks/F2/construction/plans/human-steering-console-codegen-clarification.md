# Code Generation — 사람 강제 매수(/buy) 사이징 확인 (CQ-CG)

_AI-DLC 트랙 F2 · CONSTRUCTION · Code Generation(Part 2) · 2026-05-29._
_Steps 1–7 구현·테스트 완료(브랜치 `feat/human-steering-console`). Step 8(콘솔 핸들러)에서 막힌 결정._

> 코드로 확인한 사실: `RiskManager._build_bracket_buy`(manager.py:143-201)는 매수 주식 수를
> **리스크 모델**(`position_sizer.calculate_shares`, 스탑거리 + `max_portfolio_risk` 기반)로 산정하고
> 사람이 친 `$`/`sh`를 **쓰지 않습니다**. 즉 현재 경로로는 `/buy AAPL 1000$`가 실제로 ~$1000을 사지 않습니다.
> 돈 사이징과 직결되어 임의 기본값을 두지 않고 확인합니다.

## CQ-CG1 — `/buy SYM <N$|Nsh>`의 사이징 의미
A) **사람 수량이 권위, RiskManager는 보호만** (권장) — 사람이 친 `$`/`sh`를 **그대로 체결**하고,
   RiskManager는 스탑/타겟(보호 브래킷)만 붙인다. (RiskManager에 "이 수량을 보호해서 주문 생성" 진입점 신설.)
   → 사람이 의도한 크기를 정확히 존중 + 보호 유지. 리스크 기반 포지션 사이징은 사람이 의도적으로 오버라이드.
B) **상한(cap)으로 해석, min(사람, 리스크사이즈)** — 사람 `$`/`sh`는 상한선; RiskManager가 계산한 수량과
   비교해 **더 작은 쪽** 체결. → "이 이상은 사지 마" 의미 + 리스크 모델도 유지.
C) **의도만, RiskManager가 사이징** (요구사항 FR-4 문구 그대로) — 사람의 숫자는 무시되고 리스크 모델이 사이징.
   → FR-4와 일치하나 사람이 친 숫자가 무의미해져 UX 혼란(비권장).
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: A

## CQ-CG2 — 참고(확인 불필요, 이견 시만): 매도 `sh`/`$`
`/sell SYM 10sh`·`/sell SYM 500$`는 보유 수량 대비 비율로 변환해 처리 예정 (sh→sh/보유qty, $→$/가격/보유qty,
상한 100%). `RiskManager._handle_sell`이 `sell_pct` 기반이라 이렇게 매핑합니다. 이 매핑에 이견 있으면만 적어주세요.

[Answer]: 좋음

# KIS OpenAPI 브로커 확장 — 요구사항 확인 질문

KIS OpenAPI 브로커 확장에 대한 요구사항을 명확히 하기 위해 아래 질문에 답변해 주세요.

---

## Question 1
KIS 브로커가 지원할 시장 범위는 어떻게 할까요?

A) 미국주식만 지원 (현재 autostock의 Alpaca 대체/보완 목적, 한국주식은 추후)
B) 한국주식만 지원 (새로운 시장 개척)
C) 미국주식 + 한국주식 모두 지원 (KIS OpenAPI가 둘 다 지원하므로 한 번에 구현)
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: C. 근데 조건부임. KIS의 API가 alpaca보다 편하며, 가상 paper account가 있으면 아예 다 이동 고려. 아니라면 새로운 시장 (한국시장) 개척 목적 only. 

---

## Question 2
KIS 브로커의 초기 타겟 환경은 무엇인가요?

A) 모의투자(Paper Trading)만 먼저 구현 — 실전 거래는 추후
B) 모의투자 + 실전 거래를 처음부터 모두 구현 (환경 변수로 전환)
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: B

---

## Question 3
BaseBroker 추상화 인터페이스 구현 범위는 어떻게 할까요?

A) 핵심 메서드만 우선 구현 (submit_order, get_position, get_all_positions, get_portfolio_state, cancel_order, close_position, get_order_status) — 필수 ABC 메서드
B) 핵심 메서드 + 실용적 옵션 메서드 (get_open_orders, is_market_open, get_fills, get_latest_prices, record_trade_ledger) — 가능한 모든 메서드
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: B

---

## Question 4
KIS OpenAPI 연동을 위해 필요한 한국투자증권 계좌/API 키 발급은 어떻게 진행할까요?

A) 개발자가 직접 KIS Developers Portal에서 발급 후 환경변수(.env)로 제공한다고 가정하고 진행
B) 계좌 개설부터 API 키 발급까지의 가이드 문서를 함께 작성해줬으면 함
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: A

---

## Question 5
KIS OpenAPI Python SDK 선택은 어떻게 할까요?

A) 공식 SDK 사용 (github.com/koreainvestment/open-trading-api) — 검증된 공식 라이브러리
B) 직접 REST API 호출 구현 — 의존성 최소화, autostock 스타일에 맞게 커스터마이징
C) 서드파티 SDK 검토 후 결정 (예: kis-sdk (Rust), kisopenapi (R) 등은 제외, Python 기반만 고려)
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: A

---

## Question 6: Security Extensions
보안 확장 규칙을 이 트랙에 적용할까요?

A) Yes — 모든 SECURITY 규칙을 차단 제약조건으로 적용 (프로덕션급 애플리케이션 권장)
B) No — SECURITY 규칙 건너뛰기 (PoC, 프로토타입용)
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: A

---

## Question 7: Property-Based Testing Extension
속성 기반 테스트(PBT) 규칙을 이 트랙에 적용할까요?

A) Yes — 모든 PBT 규칙을 차단 제약조건으로 적용
B) Partial — 순수 함수와 직렬화 round-trip에만 PBT 규칙 적용
C) No — PBT 규칙 건너뛰기
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: B

# KIS 한국주식 브로커 — 추가 확인 질문

리스크 평가 결과를 반영한 수정 방향(KIS=한국주식 전용)에 대해 추가 확인이 필요한 사항입니다.

---

## Question 8
한국주식 트레이딩 유니버스는 어떻게 구성할까요?

A) KOSPI 200 + KOSDAQ 150 대형주 위주 (유동성 충분, autostock의 기존 universe 패턴과 유사)
B) KOSPI 전 종목 (약 800종목, 넓은 커버리지)
C) 사용자가 직접 종목 리스트를 지정 (설정 파일로 관리)
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: A 

---

## Question 9
한국주식 데이터 소스는 어떻게 할까요?

A) KIS OpenAPI로 시세 데이터도 통합 (단일 의존성, 하지만 rate limit 공유)
B) yfinance로 한국주식 데이터도 커버 (현재 autostock 데이터 파이프라인 유지, 별도 rate limit)
C) KIS(거래) + yfinance(시세) 하이브리드 (거래는 KIS, 분석용 시세는 기존 파이프라인)
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: A

---

## Question 10
KIS OpenAPI SDK 관련 — 공식 SDK가 `uv` 패키지 매니저 기반인데, autostock은 `pip`/`hatchling` 기반입니다. SDK 통합 방식을 어떻게 할까요?

A) 공식 SDK를 git dependency로 추가하고 필요한 부분만 래핑 (의존성 최소화)
B) 공식 SDK 없이 KIS REST API를 직접 호출하는 경량 클라이언트 구현 (자유도 높음, 유지보수 부담)
C) 공식 SDK의 구조를 참고하되 autostock 스타일로 완전히 새로 작성
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: A

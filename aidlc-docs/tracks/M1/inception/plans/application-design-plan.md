# F30 Application Design Plan

> KIS OpenAPI 브로커 확장을 위한 컴포넌트 식별, 인터페이스 설계, 의존성 정의

## 설계 범위

F30은 기존 autostock 아키텍처에 다음을 추가/수정한다:

### 신규 컴포넌트
1. **KisBroker** (`src/execution/brokers/kis_broker.py`) — BaseBroker 구현체
2. **KisDataProvider** (`src/data/providers/kis_provider.py`) — BaseDataProvider 구현체

### 수정 컴포넌트
3. **DecisionExecutor** (`src/agent/executor.py`) — bracket 검증 우회, KIS no-op 분기
4. **TradingScheduler** (`src/trading/scheduler.py`) — KST 시장 시간 지원
5. **AgentTradingMode** (`src/trading/modes/agent.py`) — KIS 브로커/스케줄러 주입

---

## 설계 질문

아래 질문에 답변 후 설계 아티팩트를 생성한다.

## Question 1
`DecisionExecutor`의 `use_bracket_orders` 검증 우회 방식을 어떻게 할까?

A) DecisionExecutor 생성자에서 `use_bracket_orders` 검증을 제거하고, 대신 `self.broker.supports_bracket_orders` 속성(기본 True)을 확인하도록 변경 → KisBroker는 `supports_bracket_orders=False`
B) `KisDecisionExecutor`를 별도 클래스로 분리하여 KIS 전용 executor로 구현
C) `use_bracket_orders=False`일 때도 DecisionExecutor가 동작하되, bracket 요구 액션(HOLD의 protection, ADJUST_STOP)을 no-op으로 처리
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: 

## Question 2
`TradingScheduler`의 KST 지원 방식을 어떻게 할까?

A) 기존 `add_market_open_job`/`add_market_close_job`에 `timezone`, `hour`, `minute` 파라미터를 추가 (기본값 US/Eastern 유지, 하위 호환)
B) `add_kr_market_open_job`/`add_kr_market_close_job` 별도 메서드 추가
C) `add_market_open_job`을 `**kwargs`를 받도록 제너럴라이즈
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: 

## Question 3
`KisBroker`에서 KIS SDK를 어떻게 초기화할까?

A) `__init__`에서 `kis_auth.KisAuth`를 직접 생성 — `api_key`, `secret_key`, `paper`에 따라 `svr` 선택
B) 팩토리 함수 `create_kis_broker(paper=True)`를 별도 제공 — 생성과 인증을 분리
C) 지연 초기화 (lazy init) — 첫 API 호출 시 인증 (토큰 만료 대응에 유리)
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: 

## Question 4
`KisDataProvider`의 `get_bars()`에서 한국주식 OHLCV 데이터를 어떻게 가져올까?

A) KIS 국내주식 API (일봉/분봉 시세 조회) — KIS SDK 의존성 유지, 단일 데이터 소스
B) yfinance로 한국주식 데이터 조회 — autostock 기존 파이프라인 활용 (yfinance는 한국주식도 일부 지원)
C) KIS API를 기본으로 하되, fallback으로 yfinance 사용 — 가용성 향상
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: 

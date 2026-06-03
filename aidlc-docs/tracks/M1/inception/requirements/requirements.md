# KIS OpenAPI 브로커 확장 — 요구사항 (v2 — 리스크 평가 반영)

## Intent Analysis

| 항목 | 내용 |
|---|---|
| **요청 유형** | New Feature (새 브로커 어댑터 추가) |
| **요청 명확도** | Clear — 리스크 평가 완료, 방향 수정 확정 |
| **범위 추정** | Single Component (src/execution/brokers/kis_broker.py) + KIS 데이터 제공자 + KIS 설정 |
| **복잡도 추정** | Moderate — REST API, 공식 SDK, 지정가 전용 리스크 관리 |

### 사용자 요청 요약 (수정됨)

autostock에 한국투자증권(KIS) OpenAPI를 **한국주식 전용** 브로커로 추가. 기존 Alpaca는 미국주식 전용으로 유지하는 멀티브로커 아키텍처. 리스크 평가(kis-risk-assessment.md) 결과 KIS 해외주식 API는 지정가만 지원하여 Alpaca의 bracket/OCO 기반 리스크 관리를 대체할 수 없음이 확인됨.

> **방향**: KIS = 한국주식(KOSPI/KOSDAQ) / Alpaca = 미국주식(NYSE/NASDAQ)  
> **리스크 모드**: KIS → `use_bracket_orders=False` (레거시 폴백) / Alpaca → `use_bracket_orders=True` (bracket/OCO)

---

## Functional Requirements

### FR-1: BaseBroker 인터페이스 구현 (한국주식 특화)
KIS OpenAPI 국내주식 API를 통해 `BaseBroker`의 모든 메서드를 구현:

| 메서드 | KIS API 매핑 | 주문 유형 |
|---|---|---|
| `submit_order(order)` | 국내주식 주문 API | 지정가(LIMIT) — 시장가도 국내주식은 가능 |
| `get_position(symbol)` | 잔고조회 API | — |
| `get_all_positions()` | 잔고조회 API (전체) | — |
| `get_portfolio_state()` | 잔고조회 + 예수금 API | — |
| `cancel_order(order_id)` | 주문취소 API | — |
| `close_position(symbol)` | 시장가 주문 제출 | — |
| `get_order_status(order_id)` | 주문내역조회 API | — |

### FR-2: 옵션 메서드
| 메서드 | 설명 |
|---|---|
| `get_open_orders(symbol)` | 미체결 주문 목록 |
| `is_market_open()` | 한국 시장 세션 확인 (09:00-15:30 KST) |
| `get_fills(since)` | 체결 이벤트 피드 |
| `get_latest_prices(symbols)` | KIS 실시간 시세 (WebSocket 또는 REST) |
| `record_trade_ledger(path, ...)` | 체결 내역 기반 round-trip 재구성 |
| `replace_order(order_id, changes)` | 주문 정정 (가능한 경우) |

### FR-3: 시장 지원
- **한국주식 전용** (KOSPI, KOSDAQ)
- 국내주식 API 사용 — 해외주식 API 대비 주문 유형이 더 다양함
- 시장가, 지정가, 조건부지정가 등 국내주식 표준 주문 유형

### FR-4: 환경 분리 (Paper / Live)
- `KIS_APP_KEY` / `KIS_APP_SECRET` — 실전
- `KIS_PAPER_APP_KEY` / `KIS_PAPER_APP_SECRET` — 모의
- `KIS_CANO` / `KIS_ACNT_PRDT_CD` — 실전 계좌
- `KIS_PAPER_CANO` / `KIS_PAPER_ACNT_PRDT_CD` — 모의 계좌
- `KisBroker(paper=True)` → 모의투자 환경

### FR-5: 공식 SDK 활용
- 공식 `open-trading-api` SDK 의존성 추가
- `kis_auth.py` 인증 모듈 래핑

### FR-6: RiskManager 연동 (Legacy Polled Mode)
- `use_bracket_orders=False` 모드에서 RiskManager가 폴링 기반 TP/SL로 동작하는지 확인
- 필요시 RiskManager에 KIS 주문 유형 제약을 반영하는 최소한의 어댑테이션

---

## Non-Functional Requirements

### NFR-1: Linux 호환성
- REST API 기반으로 WSL2에서 정상 동작

### NFR-2: 인증 및 보안
- API 키 환경변수 주입 (SECURITY-12)
- 로그 마스킹 (SECURITY-03)
- HTTPS 강제, fail-closed (SECURITY-15)

### NFR-3: 오류 처리
- KIS 오류 코드 → autostock 예외 매핑
- 토큰 자동 갱신, rate limit 백오프

### NFR-4: 테스트
- Mock 유닛 테스트 + 모의투자 통합 테스트
- PBT Partial (Hypothesis, PBT-02/03/07/08/09)

### NFR-5: 기존 시스템 통합
- BaseBroker 인터페이스 투명 주입
- TradingEngine / AgentTradingMode 변경 최소화

---

## User Scenarios (수정됨)

### Scenario 1: 한국주식 Paper Trading
1. KIS 모의투자 계좌 + API 키 발급
2. `autostock run --mode agent --broker kis --paper` 실행
3. KOSPI/KOSDAQ 종목 자동 거래
4. 콘솔에서 한국주식 포지션 모니터링

### Scenario 2: Alpaca(US) + KIS(KR) 멀티브로커
1. Alpaca(미국) + KIS(한국) 동시 운영
2. RiskManager: Alpaca = bracket mode, KIS = legacy polled mode
3. 통합 포트폴리오 콘솔

---

## Technical Decisions (수정됨)

| 결정 | 내용 | 근거 |
|---|---|---|
| 시장 범위 | 한국주식(KOSPI/KOSDAQ) 전용 | 리스크 평가: KIS 해외주식 API는 주문 유형 부족 |
| 미국주식 | Alpaca 그대로 유지 | bracket/OCO, 모든 주문 유형 지원 |
| 리스크 모드 | `use_bracket_orders=False` (폴백) | KIS는 bracket/OCO 미지원 |
| SDK | 공식 open-trading-api (국내주식) | 검증된 공식 라이브러리 |
| 주문 유형 | 지정가 위주, 시장가 제한적 | 국내주식 API 기준 |

## Extension Configuration

| Extension | Enabled | Mode |
|---|---|---|
| Security Baseline | Yes | Full |
| Property-Based Testing | Yes | Partial (PBT-02,03,07,08,09) |

## 참고 문서
- `kis-risk-assessment.md` — 상세 리스크 평가 보고서
- `requirement-verification-questions.md` — Q1-Q7 사용자 응답

# KIS OpenAPI 브로커 확장 — 리스크 사전 평가

> **평가일**: 2026-06-02  
> **평가 대상**: 한국투자증권(KIS) OpenAPI를 autostock의 새 브로커로 추가  
> **평가 목적**: KIS >> Alpaca인지 확인, API 호환성 검증, Paper 계좌 제한사항 파악

---

## 1. KIS vs Alpaca 비교 평가

### 1.1 인프라/접근성

| 항목 | Alpaca | KIS OpenAPI | 평가 |
|---|---|---|---|
| **API 유형** | REST + WebSocket | REST + WebSocket | ✅ 동등 |
| **Linux 호환** | ✅ | ✅ (REST API) | ✅ 동등 |
| **Python SDK** | 공식 `alpaca-py` (잘 관리됨) | 공식 `open-trading-api` (uv 기반) | ⚠️ Alpaca 우위 |
| **한국인 계좌 개설** | 가능 (해외 계좌) | 쉬움 (국내 증권사) | ✅ KIS 우위 |
| **Paper 계좌** | 즉시 발급, 제한 거의 없음 | 별도 발급 필요, 제한 있음 | ❌ Alpaca 우위 |
| **Rate Limit** | 200 RPM (~3.3 req/s) | 20 req/s (1200 RPM) | ✅ KIS 우위 (수치상) |

### 1.2 기능 비교

| 항목 | Alpaca | KIS OpenAPI | 평가 |
|---|---|---|---|
| **시장가 주문** | ✅ (언제든) | ❌ (MOO/MOC만, 그것도 매도 한정) | ❌ 치명적 차이 |
| **지정가 주문** | ✅ | ✅ | ✅ 동등 |
| **스탑 주문** | ✅ | ❌ | ❌ 치명적 차이 |
| **스탑-리밋 주문** | ✅ | ❌ | ❌ 치명적 차이 |
| **트레일링 스탑** | ✅ | ❌ | ❌ 치명적 차이 |
| **Bracket 주문** | ✅ (원자적, OCO와 함께) | ❌ | ❌ 치명적 차이 |
| **OCO 주문** | ✅ | ❌ | ❌ 치명적 차이 |
| **주문 정정** | ✅ (replace_order) | ❓ 확인 필요 | ⚠️ 불확실 |
| **TIF (GTC, IOC, FOK)** | ✅ | ❌ (없음, 기본 지속형) | ⚠️ 제한적 |
| **포지션/잔고 조회** | ✅ | ✅ | ✅ 동등 |
| **실시간 시세** | ✅ WebSocket | ✅ WebSocket | ✅ 동등 |
| **체결 내역** | ✅ | ✅ (주문내역조회) | ✅ 동등 |

---

## ⚠️ 정정 (2026-06-02): 해외주식 ≠ 국내주식

**중요**: 이 문서의 §1 비교표는 KIS **해외주식(미국)** API 기준으로 작성되었다. F30이
**한국주식 전용(국내주식 API)** 으로 방향을 틀면서, 주문 유형 제약이 크게 달라진다.

| | KIS 해외주식(미국) | KIS 국내주식(KOSPI/KOSDAQ) |
|---|---|---|
| 시장가 | ❌ MOO/MOC 한정, 매도만 | ✅ **ORD_DVSN=01 정상 지원 (모의투자 포함)** |
| 지정가 | ✅ | ✅ ORD_DVSN=00 |
| 조건부지정가/최유리/최우선 | ❌ | ✅ ORD_DVSN=02/03/04 등 |
| 스탑지정가 (단일 stop-limit) | ❌ | ✅ **cndt_pric 조건가격 — exchange resting order** |
| bracket (진입+TP+SL 원자적) | ❌ | ❌ 네이티브 없음 → **emulate** |
| OCO (한쪽 체결 시 자동취소) | ❌ | ❌ 네이티브 없음 → **emulate (폴링 reconcile)** |

**결론 (정정 2회 반영)**: F30(국내주식)에서는 **시장가 + 단일 스탑지정가 주문이 정상 동작한다.**
- 시장가: ORD_DVSN=01 ✅ → `supports_market_orders` 플래그 불필요
- 스탑지정가: cndt_pric로 exchange resting stop-limit ✅ → 거래소 측 보호 가능
- 원자적 bracket/OCO만 없음 → **KisBroker가 emulate** (스탑지정가 SL + 지정가 TP 개별 resting
  order + 폴링 reconcile). DecisionExecutor는 `use_bracket_orders=True`로 동작, 변경 거의 없음.
- 모의투자 제약은 주문 유형이 아니라 **호출량**(rate limit 낮음, 잔고조회 한번에 20종목).

**Option B 채택**: polled exit만이 아니라 거래소 측 스탑지정가 resting order를 주 보호로 사용
(risk-execution-redesign의 "exchange resting orders" 철학 부합), polled exit은 백업.

## 2. autostock 호환성 분석 (국내주식 기준으로 정정)

### 2.1 autostock이 사용하는 주문 유형 (from `alpaca_broker.py`)

```python
OrderType.MARKET        # 시장가 → KIS 국내주식: ✅ ORD_DVSN=01
OrderType.LIMIT         # 지정가 → KIS 국내주식: ✅ ORD_DVSN=00 (호가단위 반올림 필요)
OrderType.STOP          # 스탑 → KIS: ❌ 미지원 → polled exit으로 대체
OrderType.STOP_LIMIT    # 스탑-리밋 → KIS: ❌ 미지원
OrderType.TRAILING_STOP # 트레일링 스탑 → KIS: ❌ 미지원

OrderClass.BRACKET      # bracket(OCO) → KIS: ❌ 미지원 → use_bracket_orders=False
OrderClass.OCO          # OCO → KIS: ❌ 미지원
```

### 2.2 autostock RiskManager 의존성

autostock의 RiskManager는 `use_bracket_orders` 모드에서 다음과 같이 동작:

```
진입 주문 → BRACKET (take-profit LIMIT + stop-loss STOP)
리밸런싱 → OCO (기존 포지션의 TP/SL을 한 번에 교체)
```

이 아키텍처는 [[risk-execution-redesign]] 메모리에 명시된 대로 "exchange resting bracket(OCO) orders + LLM-suggested levels + defense-in-depth"를 구현한다.

**KIS에서는 이 전체 패턴이 불가능하다.** 브로커가 bracket/OCO를 지원하지 않으면 RiskManager는 legacy market-order + polled stop 모드로 폴백해야 한다.

### 2.3 BaseBroker 인터페이스 구현 가능성

| 메서드 | KIS 구현 가능 | 비고 |
|---|---|---|
| `submit_order` | ✅ | 국내주식: MARKET(01)+LIMIT(00)+스탑지정가(cndt_pric); BRACKET/OCO emulate |
| `get_position` | ✅ | 잔고조회 API |
| `get_all_positions` | ✅ | 잔고조회 API |
| `get_portfolio_state` | ✅ | 잔고조회 + 예수금 API |
| `cancel_order` | ✅ | 주문취소 API |
| `close_position` | ✅ | 국내주식 시장가 매도 가능 |
| `get_order_status` | ✅ | 주문내역조회 API |
| `get_open_orders` | ✅ | 미체결주문조회 |
| `is_market_open` | ✅ | 거래소별 시장 시간 |
| `get_fills` | ✅ | 체결내역 API |
| `get_latest_prices` | ✅ | 시세조회 API |
| `replace_order` | ❓ | 확인 필요 (주문정정 API 존재 여부 불확실) |

---

## 3. Paper 계좌 제한사항

### 3.1 공식 SDK에서 확인된 제한

```
"00:지정가만 가능" — 모의투자에서는 지정가(Limit) 주문만 가능
```

### 3.2 Rate Limit 경고

공식 GitHub README:
> "모의투자 계좌는 REST API 호출 제한이 낮습니다. 단일 조회에는 문제없으나, 파라미터 최적화처럼 연속 호출이 많으면 실전투자 계좌를 권장합니다."

- 실전: 20 req/s
- 모의: 더 낮음 (정확한 수치 미공개)

### 3.3 모의투자 계좌 발급

- KIS Developers Portal에서 별도 가입 + 모의투자 App Key/Secret 발급 필요
- 실계좌가 없어도 모의투자 계좌 발급 가능 여부 확인 필요
- 실전 계좌와 완전히 분리된 환경

---

## 4. 종합 리스크 평가

### 🔴 CRITICAL: 주문 유형 불일치 (Showstopper)

KIS OpenAPI 해외주식은 **지정가(Limit) 주문만 완전 지원**한다. 시장가, 스탑, 스탑-리밋, 트레일링 스탑, 브라켓, OCO가 모두 없다. autostock의 RiskManager + bracket/OCO 아키텍처와 근본적으로 충돌한다.

**영향**: KIS를 미국주식용 Alpaca 대체재로 사용하는 것은 사실상 불가능하다. autostock의 핵심 리스크 관리 패턴을 전면 재설계해야 하기 때문이다.

### 🟡 MEDIUM: Paper 계좌 기능 제한

모의투자에서는 지정가만 가능하여 백테스트/페이퍼트레이딩 시나리오가 더욱 제한된다.

### 🟢 LOW: Rate Limit

초당 20회는 autostock의 15분 턴 기반 패턴(~10-15 calls/turn)에 충분하다.

---

## 5. 권장 방향 수정

### Option 1 (권장): KIS = 한국주식 전용 브로커
```
autostock
├── Alpaca (미국주식) — bracket/OCO, 모든 주문 유형, 기존 방식 유지
└── KIS (한국주식) — 지정가 주문만, 단순화된 리스크 관리
```
- KIS의 제한된 주문 유형은 한국주식(KOSPI/KOSDAQ)에서는 오히려 자연스럽다 (한국 증시도 지정가 중심)
- RiskManager에 `use_bracket_orders=False` 폴백 모드 활용
- [[risk-execution-redesign]]의 defense-in-depth는 Alpaca에서 유지

### Option 2: KIS 미국주식 + 폴백 RiskManager (비권장)
```
KIS 미국주식 → 지정가 진입 → RiskManager 폴링 기반 TP/SL 관리
```
- bracket/OCO 없이 자체 TP/SL 관리 로직 필요
- 신뢰성 저하 (프로세스 재시작 시 리스팅 오더 소실)
- 구현 복잡도 대비 이점이 적음

### Option 3: KIS 선물옵션 API 활용 (추가 검토 필요)
- KIS는 해외선물옵션 API도 제공
- 선물옵션에서는 스탑/리밋 주문 유형이 다를 수 있음
- autostock이 선물 트레이딩을 지원한다면 검토 가치 있음

---

## 6. 결론

**KIS >> Alpaca가 아니다.** 주문 유형 측면에서 KIS는 Alpaca보다 현저히 제한적이다. KIS의 강점은 한국 거주자의 계좌 개설 용이성, 한국 시장 접근성, 더 높은 Rate Limit이다.

**수정된 전략**: KIS 브로커를 **한국주식 전용**으로 구현하고, Alpaca는 미국주식 전용으로 유지하는 멀티브로커 아키텍처로 방향을 잡는다. 이 경우 Q1의 조건부 답변 중 "한국시장 개척 목적"에 부합한다.

RiskManager는 브로커별로 다른 모드를 선택할 수 있도록 이미 설계되어 있으므로 (`use_bracket_orders`), KIS 한국주식 경로에서는 레거시 폴백 모드로 동작하면 된다.

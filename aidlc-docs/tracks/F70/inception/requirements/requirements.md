# F70 — 요구사항 분석 (섀도우 벤치마크 + alpha-vs-baseline)

> Depth: **Standard**. Brownfield. 직전 토론 + `/ai-dlc-request` UAQ 답변에 기반.
> 승인 게이트 통과 전까지 다음 단계로 진행하지 않음.

## 1. 의도 분석 (Intent)

현재 라이브 트레이딩은 `active_strategies: [llm]` — **LLM 단독**으로 운영된다. 기존 결정론적
전략(기술적 MA/RSI/MACD/Bollinger, ML RF/LSTM)과 백테스트는 라이브 경로에서 **고아 상태**다.
기술적 지표는 LLM 프롬프트의 숫자 피처로만 쓰이고, 백테스트 엔진은 `backtest` 모드 전용으로
LLM 라이브 경로와 분리돼 있다.

사용자 의도: **"기존 알고리즘·백테스트의 의미를 살리고 싶다 — 항상 다양한 기법과 비교할 수 있게
켜두기."** 합의된 해석: 결정론적 전략을 **LLM의 경쟁자/앙상블 구성원이 아니라 "측정자(benchmark)"**
로 재배치한다. 핵심 질문 하나에 답할 수 있게 만드는 것이 목표다:

> **"LLM이 비용·리스크를 감수할 만큼, 단순 baseline(buy&hold/기술적/ML)을 실제로 이기고 있는가?"**

## 2. 확정된 설계 결정 (UAQ 게이트)

| # | 항목 | 결정 |
|---|------|------|
| D1 | baseline 실행 방식 | **별도 페이퍼 계정 섀도우** — 각 baseline 전략이 sandbox account farm의 **전용 페이퍼 계정**에 실주문. 실 체결/슬리피지 반영. |
| D2 | baseline 집합 | **buy&hold + 기술적 4종(RSI·MACD·MA-crossover·Bollinger)** = 총 5 전략. **ML(RF/LSTM)은 완전 제외** — 학습 파이프라인·모델 파일이 아예 없어(코드 골격만; 미학습 시 영원히 HOLD) 의미있는 baseline 불가. 필요 시 별도 후속 트랙. |
| D3 | 결과 노출 | **전용 디렉토리에 영속 저장** — TUI/프롬프트 주입 아님. 나중에 찾아보고 이 메소드(LLM)의 정량 지표를 추출하기 좋은 데이터 스토어 형태. |
| D4 | 공정 비교 전제 | LLM과 **동일 유니버스 · 동일 가상자본 · 동일 forward 구간 · 동일 사이클 cadence** |
| D5 | extensions | 사용자 "판단 위임" → 기본값 제안 (§7). 승인 게이트에서 조정 가능. |

## 3. 기능 요구사항 (FR)

- **FR-1 (섀도우 러너).** 각 baseline 전략에 대해, 전용 페이퍼 계정에 바인딩된 트레이딩
  사이클을 LLM 라이브와 **동일한 유니버스·cadence**로 실행한다. 기존 `TradingEngine(broker,
  strategies)` + `BrokerApiBroker(account_id=…)` 구조를 재사용한다 (신규 엔진 작성 금지).
- **FR-2 (전략 인스턴스화).** D2의 5개 전략을 레지스트리에서 인스턴스화한다. buy&hold는 현재
  레지스트리에 없으면 신규 추가(시장/유니버스 동일가중 매수 후 보유). 기술적 4종은 기존 클래스
  재사용. **ML은 범위 밖**(§5).
- **FR-3 (계정 매핑).** baseline 전략 ↔ 전용 sandbox 계정 매핑을 설정(config)으로 관리한다.
  계정은 `scripts/broker_create_accounts.py` farm에서 할당. 매핑 누락/계정 부재 시 **fail-closed**
  (해당 baseline 스킵 + 경고, 전체 데몬은 계속).
- **FR-4 (equity 스냅샷 기록).** 사이클마다(또는 설정 주기마다) 각 baseline 계정의 equity/포지션
  스냅샷을 **전용 디렉토리**에 JSONL로 append 기록한다 (`src/core/jsonl.py` 재사용). LLM 라이브
  계정의 equity 스냅샷도 동일 스키마로 함께 기록(비교 기준선).
- **FR-5 (alpha-vs-baseline 지표 산출).** 저장된 equity 시계열로부터 정량 지표를 계산하는 순수
  함수 모듈을 둔다: 누적수익률, alpha(LLM − 각 baseline), 변동성/MDD, Sharpe 등. 출력은 동일
  전용 디렉토리에 스냅샷 파일(JSONL/report)로 영속화. **나중에 오프라인에서 재계산·추출 가능**한
  형태(원천 equity 시계열 + 파생 지표 분리 저장).
- **FR-6 (백테스트 역할 한정).** 백테스트 엔진의 용도를 "**결정론적 전략 튜닝/리그레션**"으로
  문서상 명확히 한정한다. LLM 백테스트는 룩어헤드·비재현·비용 때문에 본 트랙 범위에서 **제외**
  (코드 변경 없음, 방향성 명시). — *이 항목은 문서/주석 수준; 구현 부담 최소.*
- **FR-7 (온오프 토글).** 섀도우 벤치마크 전체를 켜고 끄는 마스터 설정(기본값은 §6 NFR에서 결정).
  꺼져 있으면 추가 계정 호출/주문이 전혀 발생하지 않는다.

## 4. 비기능 요구사항 (NFR, 초안 — Construction NFR 단계서 정련)

- **NFR-1 (프로덕션 무영향).** baseline 섀도우는 **별도 sandbox 계정**에서만 거래한다. LLM 라이브
  계정/주문 경로를 절대 건드리지 않는다 (계정 ID 격리, fail-closed).
- **NFR-2 (운영 부담 한계).** 5개 baseline × 동일 cadence의 추가 API 호출이 rate-limit·데몬 사이클
  지연을 유발하지 않도록 한다(병렬/순차 + 백오프 고려). cadence는 LLM과 정렬하되 과도하면 down-sample.
- **NFR-3 (저장 비용).** equity 스냅샷은 append-only JSONL, 합리적 보존 정책. 무한 증가 방지.
- **NFR-4 (재현 가능 분석).** 원천 equity 시계열을 보존해 지표 계산식이 바뀌어도 과거를 재산출 가능.

## 5. 범위 밖 (Out of Scope)

- **ML baseline(RF/LSTM)** — 학습 파이프라인·모델 파일 부재로 F70에서 완전 제외(D2). 후속 트랙 여지.
- LLM을 baseline과 **앙상블/투표로 섞기** (명시적으로 안 함 — 측정만, 경쟁 아님).
- baseline 신호를 LLM 프롬프트에 **피드백 주입** (UAQ에서 미선택; 향후 후속 트랙 여지).
- TUI/Operator Console 상시 표시 (UAQ에서 "전용 디렉토리 저장"만 선택).
- LLM 자체의 백테스트.
- 실자본(live) 거래 — 페이퍼/샌드박스만.

## 6. 미해결/가정 (승인 시 확정)

- **A1 (계정 수급).** sandbox farm에 baseline 7개에 할당할 페이퍼 계정이 충분히 있다고 가정.
  부족 시 `broker_create_accounts.py`로 증설하거나, baseline을 한 계정 내 **가상 서브포트폴리오**로
  근사(차선책)할지는 Application Design에서 결정.
- **A2 (cadence).** baseline 사이클을 LLM intraday cadence와 정확히 1:1로 맞출지, EOD 1회
  스냅샷으로 down-sample할지는 NFR 단계에서 확정(NFR-2와 연동).
- **A3 (ML 모델).** ~~RF/LSTM 모델 부재 시 fail-closed 스킵~~ → **해소: ML 완전 제외로 확정**
  (2026-06-07). ML 전략은 학습 파이프라인·모델 파일이 전무(코드 골격만, 미학습=영원히 HOLD)해
  baseline 무의미. 필요 시 "ML 학습 파이프라인" 별도 트랙으로 분리.

## 7. Extension 기본값 제안 (D5 — 승인 게이트에서 확정)

- **Security Baseline: Enabled (대부분 적용 가능 범위 한정).**
  - 적용: 추가 sandbox 계정 자격증명/`account_id`의 안전 취급(fail-closed, 로그 마스킹 —
    기존 `BrokerApiBroker` 패턴 준수), 저장되는 benchmark 파일에 시크릿 미포함.
  - N/A: 인증/인가 흐름, 외부 노출 엔드포인트 (본 트랙은 내부 측정·로컬 파일 저장이라 해당 없음).
- **Property-Based Testing: Enabled (Partial).**
  - 적용: equity/alpha 지표 계산 순수 함수(FR-5), JSONL 직렬화 라운드트립(FR-4)에 PBT.
  - 제외: 브로커 I/O·계정 호출 등 부수효과 경로(통합/스모크 테스트로 커버).

## 8. 영향 코드(예상) — Application Design에서 확정

- `config/strategies.yaml` 또는 신규 `config/benchmark.yaml` — baseline 목록 + 계정 매핑 + 토글.
- `src/strategy/` — buy&hold 전략 신규(레지스트리 등록), 기존 기술적/ML 재사용.
- 신규 모듈(예: `src/benchmark/`) — 섀도우 러너 오케스트레이션 + equity 스냅샷 기록 + 지표 산출.
- 전용 저장 디렉토리(예: `data/benchmark/`) — equity 시계열 + 파생 지표 JSONL.
- `src/execution/brokers/broker_api_broker.py` — 재사용(변경 최소). 다계정 인스턴스화.
- `main.py` / 데몬 사이클 — 섀도우 러너 훅(토글 기반).

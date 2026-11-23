# 요구사항과 구현 계획

## 사용자 시나리오

1. 요율이 만료되면 수동 수정 없이 API 재조회한다. 실패 시 0원/이전 요율로
   계속 거래하지 않고 명시적으로 보류한다. 연간 양도소득세는 계산하지 않는다.
2. Toss 미국 주식과 사용 가능한 USD 현금을 한 번 복제해 독립 가상 계좌를 만든다.
   이후 실제 입출금/거래를 재동기화하지 않으며 같은 초기 자산의 buy-and-hold와 비교한다.
3. 에이전트 판단과 체결은 별도로 기록한다. 재시작해도 잔고/주문/수수료/실험 기한과
   에이전트 호출 한도가 유지된다. 보고서만으로 운영/데이터 오류와 가상 성과를 구별한다.

## 설계

- CommissionSchedule: 계좌별 private cache, KST 포함 종료일과 최대 6시간 TTL 중
  빠른 시각에 재조회. 유효하지 않은 응답/오래된 캐시에는 fallback하지 않는다.
- TossShadowBroker: TossClient(read_only=True), durable JSON transaction + file lock.
  초기 USD 부분 자본만 복제(완전한 Toss NAV 아님). 현물 long-only, 비대출.
- 체결: 주문 이후의 유효한 bid/ask, 설정 지연, 잔량 참여율, 추가 adverse slippage.
  limit은 실제 시장성 조건, 미체결/부분 체결, 같은 book 재소비 금지. 보호 주문은
  로컬 모의 실행임을 명시하고 가격 gap을 손절 지정가로 과대평가하지 않는다.
- 비용: API 수수료 + 날짜가 있는 미국 매도 규제비용 가정. 계좌 맞춤 수수료와
  추정 세금은 분리 기록. USD 원장(자동 환전 없음), 연간 양도세 제외.
- CLI init / run / report: 독립 workspace, bounded days + max turns/day, 기존 agent
  및 RiskManager 재사용. 실제 Toss 주문 및 Alpaca 접근 없음. polling 체결은
  LLM 실행 중에도 계속한다. 단기 결과는 거래 수익 향상 증거로 단정하지 않는다.

## 구현 순서

1. [x] src/execution/brokers/toss/costs.py 및 broker/account wiring, 만료 경계 테스트.
2. [x] src/execution/brokers/toss/shadow.py: 가상 장부, 체결, cost attribution, baseline.
3. [x] src/evals/toss_shadow.py: 시드/운용/보고 CLI, factory/config 연동과 agent 격리.
4. [x] 재시작/부분 체결/비용/호가/계좌 분리/runner 회귀 테스트; 전체 Python suite.
5. [x] docs/TOSS.md 및 post-merge-guide, 실제 GET-only smoke; 로컬 통합 대기.

## 검증 한계

Toss 호가는 NBBO 전체가 아니며 queue priority, 실제 라우팅 지연, 시장 충격을
관측할 수 없다. 배당/분할/합병은 자동 반영하지 않는 단기 평가 모델이다.
가정과 미지원 항목을 보고서에 항상 노출한다. Alpaca 계좌 복제는 이번 범위에서 제외한다.

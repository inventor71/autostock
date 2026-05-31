# F9 — Component Dependency

## 의존 매트릭스

| Component | 의존 대상 | 통신 방식 |
|-----------|-----------|-----------|
| C1 ConsoleOrderTools (TS) | C2 계약(args 모양), FileDrop | 파일드롭(commands.jsonl, +token) |
| C2 SteeringContract | — (양 언어가 함께 따름) | golden contract.json + 계약 테스트 |
| C3 CommandHandler (Py) | C2 계약, C4 Order, C5 게이트, C6 브로커 | in-process 호출 |
| C4 OrderModel (Py) | types.py(enum) | pydantic |
| C5 HumanOrderRiskGate (Py) | C4 Order, position_sizer, data_provider(가격) | in-process 호출 |
| C6 AlpacaBrokerOrders (Py) | C4 Order, alpaca-py SDK | HTTPS(Alpaca) |

## 빌드 순서 (bottom-up, forward-stub 최소화)
```
U-RISK (C4 OrderModel → C6 Broker → C5 RiskGate)
   → U-DAEMON (C3 Handler + C2 Python 계약측)
      → U-CONSOLE (C1 Tools + C2 TS 계약측 + parser 트림)
```
- C5는 C4에 의존하므로 C4 먼저. C3는 C4/C5/C6 모두 필요 → U-RISK 후 U-DAEMON. C1은 C2 계약 모양만
  알면 되므로 마지막. 교차언어 계약 테스트는 U-CONSOLE 완료 시 최종 green.

## 데이터 흐름 (주문)
```
[opencode AI] --tool args--> [C1 zod] --send(place_order,args)+token--> commands.jsonl
   --> [C3 _v_place_order] --PlaceOrderArgs(C2)--> [C4 Order draft]
   --> [C5 receive_human_order(force)] --(accept|clamp)--> [C6 submit_order] --> Alpaca
                                       --(reject)--------> events.jsonl(outcome+suggestion)
```

## 결합/경계 주의
- **계약 결합(C1↔C3 via C2)**: verb/args 드리프트는 런타임 reject로만 드러남 → C2 계약 테스트가
  per-verb args까지 고정해야 차단(NFR-3). 신규 verb 추가 시 records.py `Literal` + schema.ts
  `ALL_VERBS` + contract.json **3곳 동시 수정**.
- **C5 ↔ evaluate_signal 분리**: 휴먼 게이트(C5 신규)와 에이전트 게이트(`evaluate_signal`)는 헬퍼
  (`_resolve_stop`, position_sizer, breaker/pool 플래그)만 공유하고 **진입점은 분리** → 휴먼 경로
  변경이 에이전트 경로를 회귀시키지 않음.
- **C6 브로커 추상**: 신규 메서드는 `BaseBroker`에 기본 구현(loop/no-op) 제공 → 시뮬/백테스트
  브로커가 깨지지 않음.
- **권한 경계(NFR-1)**: C1(콘솔 MCP)만 주문 tool 보유. 에이전트 세션은 이 MCP 미구성 + 토큰 스크럽
  + deny-hook + 데몬 토큰 체크. F9는 새 도달면 미추가.

# F9 — Services / Orchestration

> 서비스 = 컴포넌트를 가로지르는 오케스트레이션 경로. F9는 신규 서비스 프로세스를 만들지 않고
> **기존 콘솔↔데몬 파일드롭 파이프라인의 계약과 게이트를 교체**한다.

## S1. 주문 배치 오케스트레이션 (place_stock_order)

```text
운영자 NL
  → opencode 콘솔 AI (구조화 tool 선택)
  → ConsoleOrderTools.place_stock_order(args)   [C1, zod 검증]
  → opencode permission `autostock_place_stock_order:"ask"`  [휴먼 컨펌, FR-4]
  → FileDrop.send("place_order", args)  → steering/commands.jsonl (+token, confirmed=true)
  → 데몬 CommandHandler._v_place_order  [C3]
       → PlaceOrderArgs 파싱 (per-verb 계약, C2)
       → Order 초안 구성 (C4)
       → RiskManager.receive_human_order(order, force)  [C5]
            ├─ 통과/clamp → Broker.submit_order(order)  [C6] → 주문(들)
            └─ reject → OrderDecision(accepted=false, reason_code, suggestion)
  → events.jsonl outcome emit  [토큰 비노출, FR-6 제안 포함]
  → 콘솔 AI가 결과/제안을 운영자에게 설명 (필요시 수정 재제출)
```
- **오프아워**: 시장 미개장이면 기존처럼 큐잉(`queue_offhours`) 후 `deferred` outcome.
- **override**: `force=true`는 budget/pool/breaker만 우회. price-sanity·auto-protect는 항상 적용.

## S2. 주문 관리 오케스트레이션 (cancel/replace/close)

```text
ConsoleOrderTools.{cancel_order_by_id|cancel_all_orders|replace_order_by_id|
                   close_position|close_all_positions}
  → opencode ask → FileDrop.send(verb,args)
  → CommandHandler._v_{cancel|cancel_all|replace_order|close_position|close_all}
  → Broker.{cancel_order|cancel_all_orders|replace_order|close_position|close_all_positions}
  → outcome emit
```
- **replace (Q2=A)**: 대상이 bracket/oco leg를 가진 주문이면 게이트 이전에 reject + "cancel 후
  재place 안내". 단순 미체결 주문만 Alpaca 네이티브 replace.
- **cancel_all/close_all**: Alpaca 네이티브 우선, 미지원 브로커는 loop 에뮬(기존 패턴).

## S3. 안전/lifecycle 결정적 경로 (변경 최소, FR-2 하이브리드)

```text
운영자 "/kill" 등
  → opencode AI (또는 직접) → 결정적 verb 매핑(트림 parser / verb-name tool, LLM 해석 아님)
  → DESTRUCTIVE_VERBS(kill/flatten_all)는 CONFIRM 키워드 게이트 유지
  → FileDrop.send(verb,{}) → CommandHandler._v_{kill|halt_entries|pause|...}  [기존 그대로]
```

## S4. advisor 에이전트 경로 (무변경, NFR-1)

```text
research/intraday/PM agent → decisions.jsonl → DecisionExecutor
  → RiskManager.evaluate_signal  [기존 게이트, F9 미변경]
  → Broker.submit_order
```
- F9는 이 경로에 **신규 도달면을 추가하지 않음**. 토큰 스크럽 + PreToolUse deny-hook + 데몬 토큰
  체크의 defense-in-depth 유지(NFR-1). 새 주문 tool은 콘솔 MCP에만 등록.

## 오케스트레이션 원칙
- **단일 권위 게이트**: 모든 주문(휴먼 신규/관리)은 데몬 측 RiskManager/Broker를 통과(fail-closed,
  NFR-4). 콘솔 zod는 1차 방어일 뿐 최종 권위가 아님.
- **계약 우선**: per-verb args 계약(C2)을 parser 주문문법 제거 전에 고정(NFR-3).
- **부수효과 보존**: 심볼 락/오프아워 큐/ reconcile/ outcome emit 등 기존 동작 유지.

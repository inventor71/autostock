# F9 요구사항 질문 (v3 — 재설계: 구조적 Alpaca-shaped 게이팅 MCP 툴)

> 트랙: **F9 — 게이트 계약을 "슬래시 문자열"에서 "구조적 Alpaca-MCP 형태 툴 호출"로 전환**
> `[Answer]:` 뒤에 보기 letter를 적어주세요. 맞는 게 없으면 `X) 기타`에 설명. 끝나면 "완료".

## 확정된 설계 전제 (사용자 명확화로 결정됨 — 더 묻지 않음)

- 운영자는 슬래시를 직접 안 씀 → NL로 말하고 opencode AI가 현재는 슬래시 문자열 `steer({command})`
  툴로 변환. 이 슬래시 문법(시장가 전용)이 빈약함의 원인.
- **새 계약**: opencode AI가 **구조적 Alpaca-shaped MCP 툴**(`place_stock_order` 등 JSON args)을
  호출 → opencode `ask`로 사람 확인 → 구조적 SteeringCommand + 토큰 + file-drop → 데몬
  **RiskManager/Broker 게이트 → order(s)/reject**.
- 슬래시 명령은 **AI가 알아듣는 간편어로 강등**(대화/비주문 lifecycle 용). 게이트 계약 아님.
- advisor-only research/intraday/PM 에이전트(decisions.jsonl 경로)는 **불변**.
- 사람 확인은 opencode 권한 `ask`로 유지(운영자 콘솔 AI는 제안만, 자동 체결 아님).

이제 남은 결정 사항만 묻습니다.

---

## Question 1 — 미러링할 Alpaca 툴 표면 범위 (구조적 게이팅 툴로 만들 대상)
어디까지를 구조적 Alpaca-shaped *게이팅* 툴로 만들까요? (누적 티어)

A) **주식 주문 라이프사이클만** — `place_stock_order`(풀 파라미터) + `cancel_order`/
   `cancel_all_orders` + `replace_order` + `close_position`/`close_all_positions`. 읽기/시세는
   기존 read 도구 유지. (요청 핵심에 집중, 권장)
B) A + **크립토 주문**(`place_crypto_order`)
C) A + **옵션 주문/행사**(`place_option_order` 단일·멀티레그, exercise/DNE)
D) A + B + C + 계정/워치리스트 mutation까지 — Alpaca 풀 패리티
X) 기타 (아래 [Answer]: 태그 뒤에 직접 기술)

[Answer]: A 

## Question 2 — RiskManager가 완성형 주문을 "받는" 방식 (핵심)
구조적 Alpaca 주문(qty/notional·order_type·가격·TIF·order_class 명시)을 게이트가 어떻게 처리?

A) **검증자 + 자동 보호 보충(hybrid, 권장)** — 호출자 명시값을 존중하되: ① 수량/노출이 리스크
   예산 초과면 **거부 또는 클램프**, ② 보호(stop/take-profit) 미지정 시 ATR/레벨 기반 **자동 부착**,
   ③ 가격 정합성(롱인데 시장가 위 스탑, 비현실적으로 먼 지정가 등) **거부**. 결과는 order(s)/reject.
B) **순수 검증자(pass/reject만)** — 명시값 그대로, 한도/정합성 위반만 거부. 자동 보호 부착 없음
   (보호는 호출자 책임). 최소 간섭, Alpaca와 가장 1:1.
C) **구성자 유지(자문-보강)** — 호출자는 의도/레벨만 제안, RiskManager가 여전히 사이징+주문 구성
   (현행 모델 유지, Alpaca 파라미터는 힌트로만)
X) 기타 (아래 [Answer]: 태그 뒤에 직접 기술)

[Answer]: A

## Question 3 — "거부(reject)" 결과를 호출자에게 어떻게 돌려줄까
RiskManager가 주문을 거부/클램프할 때 운영자 콘솔 AI가 받는 피드백 형태는?

A) **구조적 사유 + 제안** — 거부 사유 코드/메시지 + (가능하면) 통과 가능한 클램프 제안(예:
   "수량 100→37로 줄이면 통과")을 MCP 결과로 반환해 AI가 운영자에게 설명/재시도 (권장)
B) **단순 거부 메시지** — 사유 문자열만 반환 (현행 `_emit` outcome 수준)
X) 기타 (아래 [Answer]: 태그 뒤에 직접 기술)

[Answer]: A

## Question 4 — 슬래시 파서(parser.ts)와 비주문 lifecycle 동사의 처리
주문이 구조적 툴로 가면, 기존 슬래시 파서와 lifecycle 동사(pause/kill/approve/directive/answer/
unlock/note)는?

A) **주문은 구조적 툴, lifecycle/approval/context는 기존 `steer` 문자열 유지** — 둘 다 공존,
   파서는 lifecycle용으로 남김 (변경 최소, 권장)
B) **모든 동사를 구조적 툴로 전환** — lifecycle/approval도 구조적 MCP 툴로, 슬래시 파서 제거
C) **슬래시 파서를 AI 간편어 해석기로만 유지** — AI가 슬래시를 받으면 내부적으로 구조적 툴로 환산
X) 기타 (아래 [Answer]: 태그 뒤에 직접 기술)

[Answer]: B

## Question 5 — notional($) × 비시장가 (Alpaca 구조적 제약)
Alpaca는 notional/금액 주문을 사실상 시장가·DAY로만 허용(지정가/스탑엔 정수 수량 필요).

A) **검증 차단(fail-closed)** — 금액 notional은 시장가에서만 허용, 지정가/스탑엔 수량만, 위반 시
   구조적 거부 사유 반환 (권장)
B) **자동 환산** — 금액 지정가 입력 시 지정가로 수량 내림 환산 + echo 명시
X) 기타 (아래 [Answer]: 태그 뒤에 직접 기술)

[Answer]: A

## Question 6 — 툴 명명/시그니처를 Alpaca와 1:1로 맞출까
구조적 게이팅 툴의 이름/파라미터를 Alpaca MCP와 동일하게(`place_stock_order` 등) vs 프로젝트 고유?

A) **Alpaca MCP와 동일 명명/시그니처** — 미래에 Alpaca MCP ↔ 우리 게이팅 레이어 교체/대조가 쉬움,
   Alpaca 문서 그대로 통용 (권장)
B) **프로젝트 고유 명명** — 우리 도메인에 맞춘 이름(예: `gated_order`), Alpaca는 내부 매핑
X) 기타 (아래 [Answer]: 태그 뒤에 직접 기술)

[Answer]: A

## Question: Security Extensions
보안 확장(SECURITY-*) 강제? (주문 권한 경계/토큰 처리 변경이 커서 SECURITY-11/03 특히 중요)

A) Yes — 모든 SECURITY 규칙 blocking 강제 (권장)
B) No — 생략 (PoC/실험용)
X) 기타 (아래 [Answer]: 태그 뒤에 직접 기술)

[Answer]: A

## Question: Property-Based Testing Extension
PBT 강제? (구조적 주문 검증, 금액↔수량 환산, 보호 레벨 산출 등 순수 함수 다수 생김)

A) Yes — 모든 PBT 규칙 blocking 강제
B) Partial — 순수 함수/직렬화 라운드트립에만 (기존 트랙 기본값, 권장)
C) No — 생략
X) 기타 (아래 [Answer]: 태그 뒤에 직접 기술)

[Answer]: B

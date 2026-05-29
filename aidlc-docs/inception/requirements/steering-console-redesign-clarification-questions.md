# F4 — Steering Console 재설계 — 해명(Clarification) 질문

답변에서 **모순 1건**과 **스코프 확인 1건**이 나와, 진행 전에 정리가 필요합니다.
`[Answer]:` 뒤에 letter로 답해주세요. 다 되면 "완료"라고 알려주세요.

---

## 모순 1: "F2 폐기"(Q1=C, Q7=C) ↔ "F2 CommandBus 재사용"(Q3=A)

- **Q1=C / Q7=C**: F2를 거의 폐기하고 처음부터 재설계, F2 브랜치도 폐기.
- **Q3=A**: 운영자 세션 → 데몬 통신은 **F2 NFR-1의 단일 직렬화 CommandBus**에 file-drop으로 넣고
  **같은 안전 게이트로 처리**(기존 직렬화 불변식 재사용).

문제: F2의 **데몬측 엔진** = 단일 직렬화 command path + `DecisionExecutor`→`RiskManager`→`Broker`
안전 게이트 + reconcile turn + human-approval 게이트 + `SteeringState`. 이게 **라이브 주문 안전성의
핵심**(268 테스트)이고 Q3=A가 재사용하려는 바로 그것이다. "폐기"와 "재사용"이 동시에 참일 수 없다.

### Clarification Question 1
"F2 폐기"의 정확한 범위는?

A) **브랜치 코드 + 프론트엔드(`console.py`) + parser는 폐기**하되, **데몬측 안전 아키텍처**(직렬화
   command path, executor→RiskManager→Broker 게이트, reconcile, approval 게이트, SteeringState)는
   **개념으로 채택**하고 F4에서 **Claude-Code-native + file-drop로 깨끗이 재구현**한다.
   ("처음부터"=branch 살라미가 아니라 fresh 구현, 단 같은 안전 모델.) — Q3=A와 정합. (권장)
B) 데몬측 안전 메커니즘까지 **요구사항부터 다시 도출**해 완전 그린필드로 만든다(F2와 달라질 수 있음).
   → 라이브 주문 경로를 처음부터 재검증해야 하므로 위험·작업량 최대.
C) 사실은 **데몬측 엔진은 그대로 살려 머지(Q1=A)** 하고, 프론트엔드/브랜치 정리만 새로 한다
   (즉 Q1/Q7을 A로 정정).
X) 기타

[Answer]: A

---

## 스코프 확인: opencode fork(Q2=B) + 데몬 재구현 + F3 재정렬(Q7=C)

Q2=B(opencode fork) + Q1=C(데몬 재구현) + Q7=C(F3도 F4 기준 재정렬)를 합치면 **F2보다 훨씬 큰
스코프**다. opencode fork TUI와 안전한 주문 경로(파일-드롭 계약·게이트)는 **독립적으로** 만들 수
있고, 후자를 먼저 완성하면 헤드리스로도 검증 가능하다.

### Clarification Question 2
구현 **순서/단계**를 어떻게 가져갈까?

A) **계약 우선, TUI 나중** — v1 = deterministic file-drop 명령 계약 + 데몬측 안전 게이트(헤드리스로
   CLI 테스트 가능) + Claude Code로 임시 운전. v2 = 그 위에 opencode fork TUI. opencode가 v1을
   막지 않음. (권장: 안전 경로를 먼저 굳힘)
B) **opencode fork를 v1부터** 1급 deliverable로 함께 구축(계약과 TUI 동시).
C) opencode 없이 **Claude Code custom command만으로** 충분한지 먼저 검증하고 fork는 보류
   (Q2를 사실상 C/A로 재고).
X) 기타

[Answer]: B

---

## 참고: 확정으로 기록할 항목 (모순 아님 — 확인만)

아래는 모순이 아니어서 그대로 요구사항에 반영합니다. 이의 있으면 위 [Answer] 옆에 적어주세요.
- **Q4=B**: 자연어 매매 허용 + echo/`y`·`CONFIRM` confirm 게이트. LLM은 *제안*만 하고, 확인 게이트
  + RiskManager 게이트가 방어선. (주문 경로 비결정성은 confirm으로 차단.)
- **Q5=A,C,D + B 일부**: 읽기/이벤트 푸시/양방향 질의를 v1, 쓰기·조종(지시 주입 등)은 일부만 v1, 확장.
- **Q6=A**: 완전 detached. **Q9=A**: 확장 기본 유지.
- **Q8 핵심 제약(하드 요구사항으로 기록)**: 운영자 세션의 command **권한**은 research/intraday agent
  세션에서 **절대 접근 불가**여야 한다. agent 세션은 advisor-only(읽기 도구 + journal write만)이고,
  운영자 file-drop 명령 채널/주문 권한에는 **쓰기 권한이 없어야** 한다(권한 분리·SECURITY-11).

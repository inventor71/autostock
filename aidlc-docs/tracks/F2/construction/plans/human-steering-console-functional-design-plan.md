# 기능 설계 계획 — human-steering-console

_AI-DLC 트랙 F2 · CONSTRUCTION · Functional Design · 작성 2026-05-28._
_요구사항: `aidlc-docs/inception/requirements/human-steering-console.md` (승인됨)._
_실행 계획: `aidlc-docs/inception/plans/execution-plan.md` (승인됨)._

> **진행 방식:** 아래 "확인 질문"의 각 `[Answer]:` 태그를 채워주세요(알파벳, 한국어 OK,
> 맞는 게 없으면 `X) 기타` + 설명). 다 채우신 뒤 **"완료"** 라고 하시면 모호한 답변을 점검하고
> 기능 설계 산출물(business-logic-model / business-rules / domain-entities / frontend-components)을
> 작성합니다. 이 단계는 코드 없이 문서만 만들며, 콘솔 UX를 여기서 확정합니다.

---

## A. 기능 설계 작업 계획 (질문 답변 후 수행)

- [ ] **도메인 엔티티** — `HumanDirective`/개입 레코드 스키마, `Decision`의 `source` 태그(agent/human),
      lifecycle run-state(running/paused/halt-entries) 모델. → `domain-entities.md`
- [ ] **명령 문법** — 정형 동사 집합, 인자 형태(크기·비율·가격), 파싱 규칙, 자유 형식 note/directive. → `business-logic-model.md`
- [ ] **비즈니스 규칙** — 확인 흐름, 강제 매매→`DecisionExecutor` 매핑(동일 RiskManager 게이트),
      paused/halt-entries 게이팅, reconcile 트리거 규칙, 사람-액션이 에이전트에 주는 제약. → `business-rules.md`
- [ ] **데이터 흐름** — 콘솔 입력 → 직렬화 명령 경로 → executor/orchestrator → 저널 채널(`human_directives.jsonl`)/로그. → `business-logic-model.md`
- [ ] **콘솔 UX** — 프롬프트/출력/도움말/로그 처리/에러·확인 메시지(콘솔이 이 기능의 UI). → `frontend-components.md`
- [ ] **에러 처리** — 파싱 실패/미확인/타임아웃 fail-closed; reconcile 실패 격리(데몬 비중단). → `business-rules.md`
- [ ] **테스트 속성(PBT-01)** — 파서 불변식, `HumanDirective` 직렬화 라운드트립 식별. → 각 산출물에 "Testable Properties" 절

---

## B. 확인 질문 (콘솔 UX 중심)

### 질문 1 — 강제 매수(buy) 크기 지정 방식
A) 노셔널 금액($) — 예 `buy AAPL 5000` = $5,000어치. RiskManager가 한도 내에서 사이징·보호.
B) 주식 수 — 예 `buy AAPL 10` = 10주.
C) RiskManager 위임 — 예 `buy AAPL`(크기 미지정) → 평소 에이전트 매수처럼 기본 사이징.
D) 셋 다 지원 (권장) — `buy AAPL $5000`(금액), `buy AAPL 10sh`(주식 수), `buy AAPL`(미지정→RiskManager 위임).
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: A + B. 명령은 /command로 작성. /buy AAPL {10$, 10sh}의 두가지 postfix만 accept. 단위가 없거나 $,sh가 아닐시 reject하고 이유 설명.

### 질문 2 — 매도(sell) 인자/기본값
A) `sell AAPL` = 100% 전량, `sell 50% AAPL` = 부분. (권장)
B) `sell AAPL` 도 항상 비율 명시 요구(실수 방지).
C) 인자 순서를 `sell AAPL 50%` 형태로 선호.
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: B. /sell AAPL {50%, 10sh, 500$} 식의 세가지 postfix만 받음

### 질문 3 — 콘솔 출력 & 로그 처리 (UX 핵심)
콘솔이 붙어 있는 동안 스케줄러 로그(loguru)와 입력 프롬프트가 섞이는 문제를 어떻게?
A) 콘솔 붙은 동안 loguru의 **stdout 출력을 끄고 파일(`logs/autostock.log`)로만** 보냄 — 프롬프트가 깨끗;
   필요 시 `log tail` 류 명령으로 최근 로그 확인. (권장)
B) 로그도 화면에 계속 흐르게 두고 프롬프트는 그 사이사이에 표시.
C) 화면 영역 분리(상단 로그 / 하단 입력) — UX는 좋지만 추가 라이브러리(prompt_toolkit 등) 필요(요구사항의
   "신규 런타임 의존성 0" 목표와 상충).
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: A로 해결. 현재 어차피 scripts/monitor.sh를 이용해서 보고 있음. 콘솔자체도 monitor.sh의 하나의 pane에 main.py를 launch하는식으로 보여주면 될듯

### 질문 4 — 명령 실행 후 피드백 (UX)
A) 해석 + 실행 결과 한 줄 요약 (예: `✓ SELL 100% AAPL — 12주 @ $190.20 체결 (order abc123)`). (권장)
B) 위 + 실행 후 해당 종목의 갱신된 포지션/보호주문 상태까지 표시.
C) 최소화 — 성공/실패만.
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: A 좋음.

### 질문 5 — 확인(confirm) 강도 (UX)
A) 모든 매매/lifecycle 변경에 `[y/N]`(기본 N); 파괴적 명령(`kill`, `flatten all`)도 동일한 y/N.
B) 일반 매매는 `[y/N]`, **파괴적 명령은 단어 확인으로 강화**(예: `flatten all` 시 `all` 또는 `CONFIRM` 재입력). (권장)
C) 확인 없음 (요구사항 Q3=B와 상충 — 비권장).
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: B가 맞는 방향. /kill, /flatten all 등의 정의가 덜된 명령이 있는거 같네 이부분은 따로 확인하는 라운드 필요!

### 질문 6 — note vs directive 구분
A) 둘 다 둠 — `note <text>`=일회성 맥락(그날 참고용), `directive <text>`=상시 지시(에이전트가 계속 준수);
   `directives`로 목록 보기, `directive clear`로 해제. (권장)
B) 하나로 통합 — `note <text>`만 두고 전부 에이전트 맥락으로 전달(상시/일회성 구분 없음).
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: A. 명령은 모두 /command로 만들기. /help도 필요할듯.

### 질문 7 — reconcile(재정렬) 턴 실행 방식
사람 개입 후 에이전트 재정렬 턴(요구사항 Q5=B)을 어떻게 돌릴까?
A) **비동기**(백그라운드)로 트리거하고 콘솔은 즉시 반환; 결과는 로그/저널에 남김.
   **트레이드·directive에만** 트리거(단순 note·읽기 명령은 다음 예약 턴에 반영). (권장)
B) **동기** — 콘솔이 재정렬 턴 완료까지 기다렸다가 요약 표시(LLM 턴이라 수 분 걸릴 수 있음).
C) 모든 개입(note 포함)마다 트리거.
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: A.

### 질문 8 — 사람 액션이 에이전트에 주는 제약 (핵심: "AI 실수 교정")
사람이 AAPL을 강제 매도(=AI 판단이 틀렸다고 보고)한 직후, 에이전트가 **다음 턴에 같은 종목을 다시 살 수** 있어야 하나?
A) **권고만** — 에이전트는 사람 액션을 인지하되 다음 턴에 자유롭게 재판단(다시 살 수도 있음).
B) **당일 보호** — 사람이 그날 강제 청산/매도한 종목은 에이전트가 **당일 재진입 금지**(사람이 `allow AAPL`로
   풀기 전까지). "AI 실수를 자연어로 교정"하려는 목적에 부합. (권장)
C) **설정 가능** — 명령별로 "일회성"인지 "당분간 지키라"인지 지정.
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: A를 하되, 에이전트의 그 종목에 대한 결정에 대해선 사람의 허락을 받아야함. 콘솔에 interactive하게 띄우게해서 y/n. 에이전트가 다시 사고 싶을시 그게 riskmanager로 들어가서 사람 결정을 대기. 사람의 결정으로 성공/실패 여부를 agent가 잘 알게 해야 함. 그렇지 않을시 무슨 이슈인지 모르고 계속 시도를 할 수 있으니. 다만, OCO 미보호건은 agent가 판단해서 등록이 가능함 (지금은 모든 종목은 보호되는걸 확인하게끔 되어있음). OCO 수정도 가능.

### 질문 9 — pause 중 동작 + 재시작 시 상태
A) `pause`는 **신규 리서치/진입만** 멈추고, 기존 포지션의 보호(스탑/OCO)·리스크 청산은 **계속 동작**(안전).
   데몬 재시작 시엔 항상 **running**으로 시작. (권장)
B) `pause` 시 reconcile/exits 포함 에이전트 활동을 **전부 정지**(단, 거래소에 이미 걸린 resting 보호주문은 유효).
C) pause 상태를 디스크에 저장 → 재시작해도 pause 유지.
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: A.

### 질문 10 — v1 읽기/보조 명령 집합
A) `status`(에이전트 상태·일시정지 여부·미체결 요약) + `positions`/`book`(현재 보유) + `help` 만. (권장)
B) 위 + `orders`(미체결 목록) + `cancel <SYM>`(해당 종목 미체결 주문 취소).
C) 최소 — `help` 만.
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: B. 근데 테스트를 할려면, paper account 하나를 더 연결하는게 낫겠나? 이 부분도 알려줘

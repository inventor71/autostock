# Functional Design Plan — Unit A: daemon-data (Python)

## 유닛 컨텍스트
daemon이 TUI에 보낼 데이터를 확장한다. 현재 `turns.jsonl`과 `Decision` 모델에 턴 ID가 없고,
`monitor.json`의 `turns.recent`/`decisions`는 포맷된 문자열 배열이라 TUI가 구조적으로 소비할 수 없다.

## 설계 범위
1. 턴 ID 생성 + `turns.jsonl` 스키마 확장
2. `Decision` 모델에 `turn_id` 필드 추가
3. `orchestrator.py`에서 턴 시작→결정 기록까지 `turn_id` 전파
4. `runtime.py`의 `publish_monitor()` 출력을 구조화된 객체로 확장
5. 턴 요약(summary) 자동 생성 로직

## 질문

아래 질문에 답변해주세요.

---

## Question 1
턴 ID 형식을 어떻게 할까요?

A) **순차 번호** — `T1`, `T2`, `T3`, ... (단순, 하루 전체 순서 파악 용이)
B) **타입 접두사 + 순차** — `R1`, `I3`, `W1`, `E1` (research/intraday/wake/eod 타입을 ID에서 즉시 파악)
C) **타입 접두사 + 날짜 내 순차** — `R1`, `I1`, `I2`, `W1`, `E1` (타입별 독립 카운터, 매일 리셋)
X) 기타 (아래 [Answer]: 뒤에 설명해주세요)

[Answer]: C

---

## Question 2
`monitor.json`의 하위호환성을 어떻게 유지할까요? 현재 `turns.recent`는 문자열 배열(`"09:43 wake $0.51 0dec"`)입니다.

A) **구조화된 객체로 교체** — `turns.recent`를 `[{id, type, ts, cost, decisions, summary, health}, ...]` 객체 배열로 변경. 기존 문자열 소비자(steer_read 등)는 함께 수정
B) **양쪽 유지** — 기존 `turns.recent`(문자열)은 그대로 두고 새 필드 `turns.detailed`(객체 배열) 추가
X) 기타 (아래 [Answer]: 뒤에 설명해주세요)

[Answer]: A

---

## Question 3
턴 요약(summary) 1-2문장은 어떻게 생성할까요?

A) **결정 기반 자동 생성** — 턴의 결정 목록에서 자동 조합 (예: "Intraday: HOLD AAPL(0.7), BUY MSFT(0.6)"). 결정 없으면 "No decisions". 빠르고 결정론적
B) **에이전트 응답 마지막 텍스트 추출** — 에이전트의 최종 응답에서 첫 1-2문장 추출. 더 자연스럽지만 파싱 필요
C) **지금은 요약 없이 결정 목록만** — 요약 필드는 빈 문자열, TUI에서 결정 목록으로 대체
X) 기타 (아래 [Answer]: 뒤에 설명해주세요)

[Answer]: A

---

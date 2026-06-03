# F47 Requirements — Clarification Questions

답변 분석 결과, 대부분 일관성 있게 선택되었습니다. 아래 3가지만 확인 부탁드립니다.

---

## Clarification 1: 급등 임계값
Q1에서 "일간 등락률 기준"을 선택하셨습니다. 급등으로 판단할 구체적인 임계값(%)은 어느 정도로 할까요?

A) +5% 이상
B) +7% 이상
C) +10% 이상
D) +15% 이상
E) 설정 파일에서 조정 가능하게 (기본값 제안: +7%)

[Answer]: B

---

## Clarification 2: 저장 경로
Q4에서 `steer 안에 watch_surge/` 라고 하셨는데, 이게 repo-root의 `steering/` 디렉토리(F4 operator-console 채널) 아래를 의미하는 건가요?
즉, `steering/watch_surge/` 에 jsonl 파일들로 저장?

A) 네 — `steering/watch_surge/YYYY-MM-DD.jsonl` (steering 채널의 read-view로 operator가 바로 조회 가능)
B) 아니요 — `workspace/watch_surge/` 아래 (에이전트 작업 공간)
C) 아니요 — `data/surge_history/` 아래 (데이터 디렉토리)
X) 기타

[Answer]: A

---

## Clarification 3: Agent 분석 프롬프트 구조
Q2=B(Agent 분석), Q3=B(자유 텍스트)를 선택하면서 "분석에 용이한 구조를 FR에서 만들어나간다"고 하셨습니다.
agent가 급등주별 원인을 완전히 자유 형식으로 작성하되, 아래 요소들을 포함하도록 프롬프트에 가이드하는 방식으로 이해하면 될까요?

A) 네 — agent에게 "각 급등주에 대해 (1)추정 원인, (2)감지 가능했을 선행 지표, (3)현재 데이터로 설명 불가능한 갭" 을 포함하도록 지시하는 semi-structured 접근
B) 완전 자유 형식 — agent가 알아서 분석하고 구조는 신경 쓰지 않음
X) 기타

[Answer]: A

---

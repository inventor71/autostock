# F49 Requirements Clarification Questions

`synthesis final verdict` drill-down 화면이 깨져서 나오는 버그 관련 질문입니다.
첨부해주신 이미지를 시스템에서 확인할 수 없어, 구체적인 증상 파악을 위해 아래 질문에 답변 부탁드립니다.

## Question 1
화면이 어떻게 깨져서 보이나요? 가장 근접한 증상을 선택해주세요.

A) 텍스트가 박스 밖으로 넘쳐서 다른 UI 요소와 겹쳐 보인다 (overflow)
B) 글자가 깨진 문자(□, �, 공백 등)로 표시된다 (character encoding/corruption)
C) 텍스트가 잘려서 일부만 보인다 (truncation)
D) 텍스트가 찌그러지거나 줄이 겹쳐서 보인다 (line overlap / layout collapse)
E) ANSI 이스케이프 코드나 마크다운 서식 문자(**, ###, | 등)가 그대로 노출되어 지저분하게 보인다
X) 기타 (아래 [Answer]: 태그 뒤에 구체적으로 설명해주세요)

[Answer]: X. 캡처 이미지를 /home/jihoonpark/Project/autostock/aidlc-docs/tracks/F49/verdict_text.png 에 넣어둠. 텍스트가 일부 겹쳐보이는 것 같음.

## Question 2
버그가 항상 발생하나요, 아니면 특정 조건에서만 발생하나요?

A) 항상 발생한다 — synthesis 텍스트를 drill-down 할 때마다 깨진다
B) 특정 턴에서만 발생한다 — 어떤 research turn은 괜찮고 어떤 턴은 깨진다
C) synthesis 텍스트가 길 때만 발생한다
D) synthesis 텍스트에 특정 문자(이모지, 표, 코드블록 등)가 포함되어 있을 때만 발생한다
E) 아직 패턴을 파악하지 못했다 — 간헐적으로 발생한다
X) 기타

[Answer]: E

## Question 3
화면이 깨지는 위치나 요소를 특정할 수 있나요?

A) overlay 박스 전체가 깨진다 (레이아웃 문제)
B) 텍스트 라인들만 깨진다 (내용 렌더링 문제)
C) 스크롤 영역이 제대로 작동하지 않는다
D) synthesis 텍스트만 깨지고, 다른 agent 평가 텍스트는 정상이다
X) 기타

[Answer]: B

## Question 4
이 버그가 발생한 턴 ID나 날짜를 특정할 수 있나요? (예: R1, R2, 특정 날짜)

[Answer]: 06-03, 21:30 근처 research로 추정. $0.93, 1dec

---

## Extension Opt-In Questions

## Question 5: Security Extensions
이 프로젝트에 Security Baseline 규칙을 적용할까요?

A) Yes — 모든 SECURITY 규칙을 blocking constraints로 적용 (프로젝트 기본값)
B) No — 이 트랙에서는 적용하지 않음 (순수 UI 표시 버그 수정)

[Answer]: B

## Question 6: Property-Based Testing Extension
이 트랙에 Property-Based Testing 규칙을 적용할까요?

A) Yes — 모든 PBT 규칙을 blocking constraints로 적용
B) Partial — 순수 함수와 serialization round-trip에만 PBT 적용
C) No — 적용하지 않음 (UI 텍스트 렌더링 버그 수정, PBT 대상 로직 없음)

[Answer]: C

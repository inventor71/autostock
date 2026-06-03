# surge-detection — Functional Design Plan

> Unit: `surge-detection` | Depth: Standard | 2026-06-03

## Plan Steps

- [ ] Step 1: 도메인 엔티티 정의 (SurgeRecord, SurgeAnalysis data models)
- [ ] Step 2: 급등 감지 로직 설계 (detector — price fetch + threshold + volume context)
- [ ] Step 3: 저장소 설계 (store — JSONL append + idempotency + read-back)
- [ ] Step 4: Agent 통합 설계 (prompt injection / tool / analysis write-back)
- [ ] Step 5: Business rules + edge cases 정의
- [ ] Step 6: 사용자 질문 해소 → 아티팩트 생성

---

## 설계 질문

아래 질문에 답변해주세요.

### Question 1
Agent가 급등주 리스트를 어떻게 전달받을까요?

A) Agent tool — `python -m src.agent.tools surge-list` 실행 시 당일 surge jsonl을 읽어 JSON으로 반환 (기존 agent tool 패턴과 일관)
B) Prompt injection — EOD review prompt에 급등주 리스트를 직접 텍스트로 삽입 (agent 별도 액션 불필요)
C) 둘 다 — tool도 제공하고, EOD prompt에도 요약을 인라인으로 포함
X) 기타

[Answer]: A

### Question 2
Agent가 작성한 급등 원인 분석을 어디에 어떻게 저장할까요?

A) Agent가 workspace 내 별도 파일에 작성 → daemon이 steering/watch_surge/로 머지 (agent는 steering/에 직접 쓸 수 없음 — PreToolUse hook 제한)
B) Agent가 `surge-analyze` tool을 통해 분석 제출 → tool이 steering/watch_surge/에 직접 append (daemon context에서 실행되므로 steering/ 접근 가능)
C) 원본 jsonl을 workspace에도 복사해두고, agent가 직접 Edit → daemon이 steering/으로 동기화
X) 기타

[Answer]: B

### Question 3
급등 감지는 EOD flow의 어느 시점에 실행할까요?

A) EOD review turn 직전 — daemon job이 market close에 surge scan 실행 → 결과를 steering/ + agent에게 전달 → EOD review turn에서 agent가 분석
B) 별도 daemon job — 시장 마감 후 독립 실행 (EOD review와 decoupled, agent 분석은 다음 day의 morning turn에서 수행)
C) orchestrator.run_eod_review() 내부에서 inline 실행 — EOD review 진입 시 먼저 scan → 결과를 prompt에 주입
X) 기타

[Answer]: A

### Question 4
급락(하한가, -7% 이하)도 함께 기록할까요? 향후 패턴 분석 대칭성을 위해?

A) Yes — 동일한 임계값(절대값 7%)으로 급락도 함께 감지하여 `direction: up/down` 필드로 구분
B) No — 지금은 급등(상승)만 기록, 필요하면 추후 추가
X) 기타

[Answer]: A

---

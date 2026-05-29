# F4 — Steering Console 재설계 (Claude Code 세션으로 교체) — 요구사항 질문

각 질문에 `[Answer]:` 태그 뒤에 보기 letter를 적어 답해주세요. 맞는 보기가 없으면
마지막 `X) 기타`를 고르고 설명을 적어주세요. 다 되면 "완료"라고 알려주세요.

---

## 0. 의도 분석 + 피드백 (먼저 읽어주세요)

**요청 요약**: 개발 중인 F2 human-steering-console(`prompt_toolkit` REPL)을 **Claude Code 세션**으로
교체. 그 세션에 다양한 custom command를 등록하고, 필요하면 **opencode.ai를 customize**한 버전을
쓴다. 목적 = (1) 자연어 명령 지원이 더 쉽고, (2) 돌아가는 intraday/research agent와 더 밀접하게
communication.

**코드 근거(중요)**:
- PM 트레이딩 **agent 자체가 이미 Claude Code 세션**이다 — `AgentSession`이 `claude -p --resume`를
  매 ET 거래일 세션으로 돌리고(tools 활성, workspace/ 에서, advisor-only), journal에만 쓴다
  (`src/agent/session.py`). 즉 "Claude 세션이 트레이딩을 운전"하는 패턴은 이미 시스템의 코어다.
- F2는 브랜치 `feat/human-steering-console`(13 커밋, 268 테스트, **머지 안 됨**)에서 이미
  **데몬측 엔진**(`src/agent/steering/{bus,commands,parser,records,state,turns}.py`) + **프론트엔드**
  (`steering/console.py`, prompt_toolkit)로 깔끔히 분리돼 있다.
- F2 NFR-1이 **이미** 단일 직렬화 command path를 설계하면서 "headless/detached용 **file-drop
  front-end**를 같은 큐로 거의 공짜로 붙일 수 있다"고 명시함 — **Claude Code 운영자 세션이 바로 그
  front-end**다. (요구사항 §6의 attached/detached 미해결 가정도 이걸로 풀림.)
- F3(intraday 재설계)는 F2의 `TurnCoordinator`/`ReconcileWorker`/`SteeringState`를 재사용하도록 설계됨.

**핵심 긴장(꼭 짚을 점)**: Claude Code/opencode의 slash command는 결국 **LLM 프롬프트로 확장**되어
모델이 도구를 호출한다. 이는 F2가 안전상 **의도적으로 LLM을 배제**한 주문 경로(FR-2 "구조화 동사,
deterministic, no LLM" / SECURITY-15 fail-closed)에 **비결정성**을 다시 들여온다. "자연어 명령이 쉽다"는
이점과 "주문 경로는 deterministic해야 한다"는 안전 제약이 정면으로 만난다 → Q4에서 결정 필요.

---

## Question 1
이번 재설계에서 **F2의 데몬측 엔진**(직렬화 CommandBus, executor 안전 게이트, reconcile turn,
human-approval 게이트, SteeringState)을 얼마나 살릴 것인가? (이게 F2의 진짜 엔지니어링이고, F3가
의존하는 부분이다. 교체 대상은 주로 prompt_toolkit `console.py` 프론트엔드다.)

A) **데몬측 엔진 전부 유지**, prompt_toolkit `console.py`만 Claude/opencode 프론트엔드로 교체
   (file-drop/IPC로 같은 CommandBus에 명령 주입). 최대 재사용, F3 영향 최소. (권장)
B) 데몬측 엔진은 유지하되 일부(parser 등 자연어로 대체되는 부분)는 들어내고 슬림화
C) F2를 거의 폐기하고 steering을 Claude-Code-native로 처음부터 재설계
X) 기타 (아래 [Answer]: 뒤에 설명)

[Answer]: C

## Question 2
운영자 콘솔의 **프론트엔드 기술**을 무엇으로?

A) **Claude Code** 그대로 + custom slash command/`CLAUDE.md`/MCP 등록 (빌드 0, 즉시 사용; 다만 UX는
   코딩 툴 제약 안에서)
B) **opencode.ai를 fork/customize**한 트레이딩-ops 전용 TUI (완전한 제어 가능하나, F2가 피하려던
   "콘솔 직접 구축" 부담이 다시 생김)
C) **단계적**: 먼저 Claude Code로 시작(v1), UX 한계가 분명해지면 opencode fork로 이전(v2)
X) 기타

[Answer]: B

## Question 3
운영자 Claude 세션 ↔ 트레이딩 데몬 간 **통신(IPC) 방식**은?

A) **File-drop 큐** — F2 NFR-1이 예고한 그 방식. 운영자 세션의 command가 JSONL/파일에 append하면
   데몬의 단일 워커가 읽어 같은 안전 게이트로 처리(기존 직렬화 불변식 그대로 재사용). (권장)
B) 데몬이 **로컬 소켓/HTTP 엔드포인트**를 열고 command를 수신
C) 데몬이 **MCP 서버**를 노출 → 운영자 Claude 세션이 MCP tool로 명령/조회
X) 기타

[Answer]: A

## Question 4
**자연어 → 매매 주문**의 안전 처리. (F2는 매매를 LLM 없는 구조화 동사로 한정했음.)

A) **Deterministic만** — slash command는 LLM이 끼지 않는 CLI(예: `steer sell AAPL`)를 호출해
   파싱/검증/enqueue. 자연어는 메모/지시(`note`/`directive`)와 조회에만. 주문 경로 비결정성 0. (가장 안전)
B) **자연어 매매 허용 + echo·confirm 게이트** — LLM이 "SELL 100% AAPL @ market"로 해석→사람이
   `y/CONFIRM` 확인해야 실행. 편의↑, 확인 게이트가 비결정성 방어.
C) **하이브리드** — 자연어로 의도 표현은 허용하되, 실제 주문은 항상 deterministic CLI 한 줄로
   환원해 보여주고 확인받음(자연어는 그 CLI로의 번역기일 뿐)
X) 기타

[Answer]: B

## Question 5
"intraday/research agent와 **밀접한 communication**"의 구체적 범위는? (복수 가능 — 예: `A,C`)

A) **읽기**: 운영자 세션이 agent의 journal/theses/turn trace를 조회(이미 `/agent-trace` 존재)
B) **쓰기/조종**: 지시 주입, reconcile turn 트리거, pause/halt/kill, 승인 게이트 처리
C) **이벤트 푸시**: 체결/결정/승인대기 발생 시 운영자 세션으로 알림(현재 F2 notify 대체)
D) **양방향 질의**: agent가 사람에게 질문을 남기고(예 "이 포지션 어떻게?") 운영자가 답하면 agent가 반영
X) 기타

[Answer]: A, C, D. B는 일부 (지시나 가이드 주입, 추후 개발하면서 확장)

## Question 6
운영자 Claude 세션과 트레이딩 **agent 세션의 관계**는? (둘 다 claude 세션이지만 별개 프로세스다.)

A) **완전 분리(detached)** — 운영자 세션은 데몬과 독립 프로세스로, 파일/IPC로만 통신. 데몬은
   foreground/tmux 없이도 무방(F2의 attached 가정 해소). (권장, A=Q3와 정합)
B) 데몬과 같은 터미널/세션에 **attach**해서 운영(F2 v1의 기존 가정 유지)
X) 기타

[Answer]: A

## Question 7
**기존 F2 브랜치/F3 의존성** 처리. (`feat/human-steering-console` 미머지, 268 테스트; F3는 F2
primitive 재사용 설계.)

A) **데몬측 엔진은 main으로 살려 머지**하고, 그 위에서 프론트엔드만 F4로 교체(F3는 그대로 그 엔진
   위에 안착). 콘솔 UI 코드(prompt_toolkit/console.py 및 그 전용 테스트)는 제거/대체. (권장, A=Q1과 정합)
B) F2 브랜치를 그대로 두고 F4를 **별도 브랜치**에서 병렬 진행, 나중에 선택
C) F2 브랜치 폐기, F3 설계도 F4 기준으로 재정렬
X) 기타

[Answer]: C

## Question 8
운영자 세션에 등록할 **custom command 세트**(v1 범위). (복수 가능)

A) **매매**: buy/sell/flatten/stop (Q4 정책 따름)
B) **라이프사이클**: pause/resume/halt-entries/allow-entries/kill
C) **승인 게이트**: pending/approve/reject/unlock (F2 FR-8)
D) **조회**: status/positions/orders/agent-trace/why/journal 요약
E) **컨텍스트 주입**: note/directive + reconcile 트리거
X) 기타

[Answer]: A,B,C,D,E. 주의 할점은 해당 운영자 세션의 command는 다른 research/intra agent에게 권한이 "확실하게" 없어야 함.

## Question 9
**확장(Extension)** 설정은 프로젝트 기본을 유지하는가? (Security Baseline = Enabled,
적용분 SECURITY-03/10/11/13/15; Property-Based Testing = Partial / Hypothesis.)

A) 예, 프로젝트 기본 그대로
B) 변경 필요 (아래 설명)
X) 기타

[Answer]: A

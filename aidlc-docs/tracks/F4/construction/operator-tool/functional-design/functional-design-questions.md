# F4 · Unit B (`operator-tool`, opencode 리브랜딩) — Functional Design 질문

운영자 측 도구(opencode 기반)의 설계 갈림길을 정리합니다. `[Answer]:` 뒤에 letter로 답해주세요.
맞는 게 없으면 `X) 기타`. 다 되면 "완료".

> **조사로 확정된 사실(읽어주세요):**
> - opencode **custom command**(`.opencode/commands/*.md`)는 본문이 **LLM 프롬프트 템플릿**이다(`!`shell`` 은 그 출력을
>   프롬프트에 주입). 즉 **결정적 동작이 아니다** → 매매 같은 안전-크리티컬 쓰기를 슬래시 명령만으로 하면 LLM이 끼어든다.
> - opencode **plugin**은 **custom tool**(Zod 스키마 + 결정적 `execute` 함수)을 등록할 수 있다 → **여기에 confirm·토큰·
>   file-drop append를 결정적 코드로** 넣으면 LLM은 *제안*만 하고 `confirmed`/토큰을 위조할 수 없다(confirm 무결성).
> - permissions(allow/ask/deny, 에이전트별)로 도구 표면을 잠글 수 있다. **알려진 버그**: `task`(서브에이전트) 우회(#5894),
>   `permission.ask` 훅 미트리거(#7006/#19927), SDK deny 무시(#6396) → 방어 설계 필요.
> - 최종 안전 경계는 **데몬측(Unit A: confirmed+토큰+RiskManager 게이트)**. opencode 잠금은 defense-in-depth.

---

> **베이스 매핑(Q2~Q7 공통):** 위 사실은 opencode 기준. Q1이 **Claude Code(A′)** 면 대응물은 — 슬래시 명령(프롬프트),
> **MCP 서버 tool**(결정적 코드 = confirm/토큰/append를 소유; 권한·hook으로 confirm 게이트), PreToolUse hook(이미 실증).
> 즉 Q2~Q7의 *의도*는 베이스 중립이고, 구체 메커니즘은 Q1이 고르는 베이스에 맞춰 설계 단계에서 확정합니다.

## Question 1 — 운영자 콘솔의 베이스 (가장 load-bearing) — *재구성*
"opencode 무-fork"는 Claude Code에 모든 면에서 밀리므로(이미 스택·hook 실증·새 툴체인 0) 제외. 진짜 선택은:

A′) **Claude Code (무-fork)** — 슬래시 명령 + 결정적 **MCP tool**(confirm/토큰/append) + 검증된 PreToolUse hook으로
   v1을 최단에 운영. 새 런타임/툴체인 0. 한계: 채팅 REPL + 슬래시/툴바까지(커스텀 TUI pane 불가, 프로그램 개조 불가).
B′) **opencode 하드 fork** — 오픈소스(TS 코어 + Go TUI)를 fork해 **프로그램 자체 개조**: 트레이딩 전용 TUI pane
   (포지션/주문/승인대기/확인모달), **LLM 우회 결정적 명령 경로**, **컴파일타임 도구 제거(권한 버그가 구조적으로 불가)**,
   이벤트 push UI, 단일 브랜드 바이너리. 더 큰 TS/Go 투자 + 두 번째 LLM 런타임.
C′) **단계적** — A′(Claude Code)로 계약·운영을 굳히고, 위 확장성이 정당화되면 **같은 Unit A 계약 위에서** B′(opencode fork)로
   이전(데몬 무변경, 되돌릴 수 있는 결정). (권장 기본값 — 단, 전용 TUI/보안 봉쇄가 v1 필수면 바로 B′)
X) 기타

[Answer]: B'.

## Question 2 — 안전-크리티컬 쓰기(매매/lifecycle/kill)의 메커니즘
`confirmed=True`를 LLM이 위조 못 하게 하는 방법은?

A) **결정적 액션 레이어** `steer(verb, args)` — 결정적 코드가 (1) 해석 1줄 에코, (2) 사람 확인(`y`/`CONFIRM`), (3) env
   토큰 부착, (4) commands.jsonl append를 **소유**. LLM은 *호출*만(args 제안), `confirmed`/토큰 위조 불가.
   *(opencode=plugin custom tool의 `execute`; Claude Code=MCP 서버 tool + 권한/hook confirm 게이트; B′ fork면 TUI 레벨
   LLM-우회 경로까지 가능.)* 서브에이전트 차단(`task` deny 또는 컴파일타임 제거). (권장 — 조사 결론)
B) 명령(프롬프트) + 사후 훅 게이트만. (LLM이 confirm 전에 끼어들 여지·권한버그로 신뢰성 의문)
X) 기타

[Answer]: A.

## Question 3 — 읽기 표면(status/positions/orders/agent-trace/why)
조회 명령은 어떻게? (읽기는 주문 권한 무관·무해)

A) **결정적 읽기 명령** — 슬래시 명령의 shell-injection 또는 읽기 전용 tool로 `steering/snapshot.json`·journal·
   `scripts/agent_trace.py`를 읽어 표시(B′ fork면 상시 패널/pane). 빠르고 데몬 라운드트립 없음. (권장)
B) LLM이 도구로 파일을 읽어 요약(유연하나 비결정·느림·토큰소모)
X) 기타

[Answer]: A.

## Question 4 — 이벤트(fills/pending/agent_question) 표면화
`steering/events.jsonl`를 운영자에게 어떻게 보여줄까?

A) **백그라운드 tail → 알림 출력**(plugin이 events.jsonl을 watch해 TUI에 push). 즉시성↑.
B) **`/inbox` 폴 명령** — 운영자가 호출하면 신규 이벤트를 모아 표시. 단순.
C) **둘 다** — 중요한 것(pending/fill)은 push, 전체는 `/inbox`.
X) 기타

[Answer]: A.

## Question 5 — 토큰 전달(운영자 프로세스 → 명령에 부착)
데몬이 발급한 토큰을 운영자 도구가 어떻게 얻나? (파일·로그 금지, BR-10.2)

A) **env 상속** — 데몬이 `STEERING_OPERATOR_TOKEN`을 자기 env에 두고, 운영자 도구를 그 환경에서 실행
   (같은 셸/런처). 도구는 `process.env`에서 읽어 명령에 실음. (권장, 현재 Unit A가 이미 env에 노출)
B) 데몬이 기동 시 토큰을 **1회 표준출력**(사람이 운영자 셸에 export)
X) 기타

[Answer]: A

## Question 6 — v1 명령 세트(운영자 도구에 노출)
어디까지 v1에? (복수 가능)

A) **매매** buy/sell/flatten/stop (결정적 tool, Q2)
B) **lifecycle** pause/resume/halt-entries/allow-entries/kill
C) **승인** pending/approve/reject/unlock
D) **조회** status/positions/orders/agent-trace/why
E) **컨텍스트/양방향** note/directive/answer(+ agent question 알림)
X) 기타

[Answer]: A-E 모두.

## Question 7 — 확장(Extension) 설정
프로젝트 기본 유지? (Security Baseline Enabled — opencode/플러그인 의존성 **버전 핀** SECURITY-10 추가 적용; PBT는
TS 측이라 결정적 환원/토큰부착 로직에 한해 example 테스트)

A) 예, 프로젝트 기본 유지(+ 베이스/플러그인/의존성 **버전 핀** SECURITY-10 + 환원·토큰부착·confirm 로직 example 테스트;
   B′ fork면 라이선스 준수 + 컴파일타임 도구 제거 검증 포함)
B) 변경 필요(아래 설명)
X) 기타

[Answer]: A

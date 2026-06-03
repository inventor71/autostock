# F39 — Normal 모드 코드 질문 차단: 요구사항 명확화 질문

> Track F39. 운영자 콘솔(opencode 포크) 에이전트가 **supervisor 모드가 아닐 때** 소스/구현 내부
> 질문에 답하지 않도록 하는 동작 강화. 아래 A/B/C/D 중 하나를 `[Answer]:` 에 적어주세요(Other 가능).

## 배경 (inception 중 코드 확인)
- **권한 벽은 이미 동작**: normal 모드에서 opencode 권한 엔진이 소스 파일 `read`/`glob`/`grep`을 차단
  (F26: `external_directory`/`read`가 `$STEERING_DIR`로만 제한, `glob`/`grep`/`lsp`는 normal에서 tool 자체 제거).
- 그런데도 transcript에서 에이전트가 (1) `src/agent/orchestrator.py`, `steer-handler.ts`를 **직접 읽으려 시도**하고
  (차단됨), (2) `/codebase` 트리 + 추측으로 **코드 내부를 설명**했다.
- 근본 원인: **운영자 전용 페르소나/시스템 프롬프트 부재** → opencode 기본 "코딩 어시스턴트" 프롬프트로 동작.
  그리고 `autostock_steer_read`(= `/codebase` 프로젝트 트리 포함, F29)가 `opencode.json`에서 **두 프로필 모두 `allow`**.

---

## Q1. "코드 질문 거부"의 범위는?
사용자 transcript의 원래 질문("왜 turn이 안 도는가")은 사실 **운영 질문**이었고, 에이전트가 이를 *소스 추측*으로
잘못 답했습니다. 거부 경계를 어디에 둘까요?

- **A.** (권장) **소스/구현 내부** 질문만 거부. 운영/런타임 상태 질문("왜 turn이 안 돌아?", "지금 포지션?")은
  `steer_read`(monitor/snapshot) 등 운영 데이터로 **계속 응답**. 단, 답할 때 **소스 추측 금지** —
  데이터로 답할 수 없으면 "supervisor 모드 필요"라고 안내.
- **B.** 코드/구현과 조금이라도 엮이면 **전면 거부**(운영 질문이라도 내부 동작 설명이 필요하면 거부).
- **C.** 거부하지 않고, 소스 추측만 금지(아는 운영 데이터로만 답하고 모르면 모른다고).

[Answer]: A — 소스/구현 내부 질문만 거부. 운영/런타임 질문은 steer_read 데이터로 계속 응답, 소스 추측 금지.

## Q2. 강제 방식(enforcement) — 어디까지 막을까?
프롬프트 가드만으로는 우회 가능(F26은 defense-in-depth 철학). 구조적 차단도 추가할까요?

- **A.** (권장) **프롬프트 가드 + 구조적 차단**: normal 모드 페르소나로 거부를 지시 **＋** 코드 지향 read 명령
  (`/codebase` 프로젝트 트리)을 normal 모드에서 **차단**(supervisor 전용). defense-in-depth.
- **B.** **프롬프트 가드만**: normal 페르소나/시스템 프롬프트로 거부하도록만 지시(`/codebase`는 그대로 둠).
- **C.** **구조적 차단만**: `/codebase` 등을 supervisor 전용으로 막되 별도 페르소나 추가는 안 함.

[Answer]: A — 프롬프트 가드 + 구조적 차단(/codebase 트리 supervisor 전용). defense-in-depth.

## Q3. `/codebase` 프로젝트 트리 — normal 모드에서 유지? (Q2=A/C 선택 시 세부)
`/codebase`는 패키지 설명이 달린 디렉터리 트리만 보여줍니다(파일 내용 아님).

- **A.** (권장) supervisor 전용으로 제한. normal에서 호출 시 "supervisor 모드 필요" 안내.
- **B.** normal에도 유지(오리엔테이션 용도). 동작 가드(추측 금지)만 추가.

[Answer]: A — supervisor 전용으로 제한(Q2=A 따라 자동). 단 Q4=B에 따라 거부 메시지에 supervisor를 언급하지 않음.

## Q4. 거부할 때 UX는?
- **A.** (권장) 정중히 거부 + **"코드/구현 질문은 `autostock --supervisor`로 다시 실행"** 안내.
- **B.** 정중히 거부만(supervisor 안내 없음 — 개발자만 아는 기능으로 유지).
- **C.** 거부 + 가능하면 운영 데이터로 부분 응답(Q1=A와 결합).

[Answer]: B — 정중히 거부만. supervisor 모드는 언급하지 않음(개발자 전용 숨은 기능 유지). → Q2/Q3의 "supervisor 안내" 문구는 이 결정으로 무효: 거부 메시지는 일반적 표현만.

## Q5. Extension opt-in
- **Security Baseline**: 이 트랙은 normal-mode 노출 표면을 *좁히는* 방향. Enable 권장(새 비밀 노출 없음 확인용).
  - **A.** Enable (권장)  **B.** Disable
- **Property-Based Testing**: 프롬프트/설정 + 작은 게이팅 로직 → 알고리즘 로직 적음.
  - **A.** Enable  **B.** Disable (권장)

[Answer Security]: A — Enable.
[Answer PBT]: B — Disable (선택 안 됨).

# F4 · Unit A (`steering-core`) — Functional Design 질문

데몬측 안전 엔진(재구현)의 설계를 굳히기 전, 진짜 갈림길 5개만 확인합니다.
`[Answer]:` 뒤에 letter로 답해주세요. 맞는 게 없으면 `X) 기타`. 다 되면 "완료".

> 참고: 아래는 모두 **Unit A(Python 데몬측)** 결정입니다. 운영자 TUI(Unit B, opencode)는 다음 유닛에서 별도로 다룹니다.
> 권장안에는 (권장) 표시.

---

## Question 1 — file-drop 채널 위치 & 권한 분리 (NFR-1 핵심)
운영자 명령을 담는 file-drop 채널을 어디에 둘까? (agent 세션 cwd는 `workspace/`이고 Read/Write/Edit
도구가 허용돼 있어, **workspace 안에 두면 agent가 명령 채널에 쓸 수 있는 권한 누수** 위험.)

A) **`workspace/` 밖** 별도 디렉토리(예: 리포 루트의 `steering/` 또는 `~/.autostock/steering/`)에 둠 →
   agent의 cwd·허용 도구 범위 밖이라 **구조적으로 agent가 명령을 못 씀**. 데몬만 읽고, 운영자 도구만 씀. (권장)
B) `workspace/` 안에 두되, agent `AgentSession`의 allowedTools/경로를 좁혀 그 하위 경로 쓰기를 차단
C) 채널은 파일이 아니라 별도 권한의 위치(OS 파일권한/소유자 분리)로 강제
X) 기타

[Answer]: A. repo root의 steering/

## Question 2 — 명령 레코드 & confirm 경계
자연어→매매의 `y`/`CONFIRM` 확인(Q4=B)을 **어디서** 처리하고, file-drop엔 무엇이 들어가나?

A) **확정 명령만 file-drop에 기록** — confirm은 운영자 도구(Unit B)에서 끝내고, file-drop에는 이미
   사람이 승인한 deterministic 명령만 append. 데몬은 confirm 개념을 모름(단순·안전). (권장)
B) **2단계** — 도구가 draft를 기록 → 데몬이 echo/검증 결과를 돌려줌 → 도구가 confirm 레코드 기록 →
   데몬 실행 (왕복 1회 추가, 데몬이 echo 책임)
X) 기타

[Answer]: A

## Question 3 — 데몬의 신규 명령 감지 방식
데몬(단일 CommandWorker)이 file-drop의 신규 명령을 언제 집어가나?

A) **스케줄러 폴링 잡**(예: 1–2초 주기 tail) — 신규 런타임 의존성 0, 기존 APScheduler 재사용. (권장)
B) **watchdog/inotify** 파일 이벤트 — 지연 최소이나 신규 의존성(SECURITY-10 핀) + 플랫폼 편차
C) 데몬이 짧은 주기로 직접 폴링(스케줄러 밖 전용 스레드)
X) 기타

[Answer]: A

## Question 4 — 명령 결과(outcome) 반환/상관
운영자가 명령을 넣은 뒤 "체결됐는지/거부됐는지"를 어떻게 받나?

A) **command id로 keyed outcome를 데몬이 events 채널에 기록** → 운영자 도구가 id로 매칭해 표시
   (요청–응답 상관 가능, FR-6 이벤트와 동일 채널). (권장)
B) outcome는 별도 상관 없이 **로그/이벤트 스트림에만** 남기고 도구는 tail만(상관 약함, 단순)
X) 기타

[Answer]: A

## Question 5 — human-approval 게이트(FR-8) v1 범위
사람이 매매한 심볼을 human-lock하고 agent 재량 BUY/SELL을 PendingApproval로 보류하는 F2 FR-8을
이번 v1에 어디까지?

A) **F2 설계 그대로 계승** — lock + PendingApproval + `/approve|/reject` + 2회 거부→당일 denied +
   재매매 reset + 보호주문/risk-exit 면제 + ET-date auto-clear. (권장: 이미 설계·검증된 안전 동작)
B) **v1 단순화** — lock + 보류/표시까지만, 거부 카운터·denied·자동해제 등은 후속
X) 기타

[Answer]: A

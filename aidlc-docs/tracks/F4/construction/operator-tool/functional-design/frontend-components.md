# 프론트엔드 컴포넌트 — Unit B `operator-tool` (F4, opencode 하드 fork)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit B · Functional Design · 2026-05-30._
_fork(B′)를 택한 핵심 이유 = 트레이딩 전용 TUI. 여기서는 화면 표면을 FD 고도로 정의(상세 위젯 구현은 Code-Gen)._

## 레이아웃 (ASCII 목업 — 표현용, 실제는 Go/Bubble Tea)
```
+----------------------------------------------------------------------------------+
| autostock-console   RUN: RUNNING   MKT: OPEN   token: ok        15:42:07 ET       |  <- 상태바
+--------------------------------------+-------------------------------------------+
| POSITIONS / ORDERS / P&L  (SnapshotView) | EVENT FEED (NotificationInbox)         |
|  AAPL  10sh  +1.2%   stop 230  oco       |  15:41 FILL  META sell 5 @ 631         |
|  META   5sh  -0.4%   stop 600  oco       |  15:40 PENDING #3 agent BUY NVDA  [!]  |
|  NVDA   --   (locked)                    |  15:38 OUTCOME #c1 executed sell AAPL  |
|                                          |  15:35 Q  agent: "re-enter META?" [!]  |
+--------------------------------------+-------------------------------------------+
| PENDING APPROVALS                      | (push 토스트가 여기로 잠깐 뜸)           |
|  #3 NVDA BUY  (agent)  /approve 3 /reject 3                                       |
+----------------------------------------------------------------------------------+
| > /sell AAPL 50%                                          (명령/자연어 입력)       |  <- 입력행
+----------------------------------------------------------------------------------+
```

## C-B1 상태바 (StatusBar)
- run_state(RUNNING/PAUSED/HALTED), market_open, **token 연결 표시**(ok/없음 — BR-B2), ET 시계, 갱신 ts.
- 데이터: `SnapshotView`(snapshot.json). 토큰 없으면 빨강 경고 + 쓰기 비활성.

## C-B2 포지션/주문 패널 (PositionsPanel) [Q3=A, fork 전용]
- 보유 수량/평단/현재가/미실현·미체결 주문(stop/oco)·락 상태. `SnapshotView`에서 렌더, 데몬 라운드트립 0.
- (무-fork였다면 불가능한 **상시 패널** — fork의 대표 이득.)

## C-B3 이벤트 피드 (EventFeedPanel) [Q4=A]
- `events.jsonl` tail. fill/pending/agent_question/outcome/reconcile 시간순. `[!]` = 행동 요망(pending/question).
- 중요한 것(pending/fill/question)은 **push 토스트**로도 잠깐 표시.

## C-B4 승인 대기 패널 (PendingPanel) [Q6-C]
- `pending` 이벤트/`snapshot.pending`에서 목록. 각 항목 `#id 심볼 동작 (agent)` + `/approve <id>` `/reject <id>` 힌트.

## C-B5 명령 입력 + 팔레트 (CommandInput) [Q2=A, Q6=A–E]
- `/`로 verb 자동완성(buy/sell/flatten/stop/pause/.../approve/reject/unlock/status/.../note/directive/answer).
- 자연어도 허용(LLM→`CommandDraft`, 1.2). 슬래시/키스트로크 매매는 **LLM 우회 결정 경로**(1.1).
- 심볼 자동완성(보유+유니버스), 명령 히스토리.

## C-B6 확인 모달 (ConfirmModal) [BR-B1, ConfirmationGate]
- 매매/파괴적 명령 시 **결정적 모달**: `echo` 1줄 + `risk_preview`(추정치 — "실행 시 데몬이 라이브 재조회" 명시) +
  `[y/N]`(파괴적은 `CONFIRM`). 통과해야만 승격(토큰+append). **LLM이 못 띄우고 못 우회**(소스 레벨).

## C-B7 결과 표시 (OutcomeToast) [BR-B6, OutcomeWaiter]
- 보낸 명령의 `corr_id` outcome 도착 시 결과(체결 수량/가격 또는 사유) 표시. 타임아웃 → "결과 미수신" 경고.

## C-B8 agent 질문 인박스 (QuestionInbox) [Q6-E]
- `agent_question` 이벤트를 모아 표시. `/answer <id> <text>`로 응답 → `SteeringCommand(answer)`.

## 상호작용 원칙
- **읽기 즉시·결정적**(패널은 파일 읽기). **쓰기는 항상 확인 모달 경유**(결정적). LLM은 NL 해석 보조일 뿐 권한 없음.
- 토큰 없음/데몬 미연결이면 쓰기 비활성·읽기 유지(BR-B2/B8).
- 콘솔 종료는 콘솔만 — 데몬 트레이딩 무영향(BR-B8).

## fork로 가능해진 것 (무-fork 대비) — 요약
상시 포지션/주문/P&L 패널(C-B2), 승인대기 패널(C-B4), 이벤트 push 피드(C-B3), **LLM 우회 결정 매매 경로**(C-B5/1.1),
**결정적 확인 모달**(C-B6, 소스 레벨), 컴파일타임 도구 봉쇄(BR-B4), 단일 브랜드 바이너리. → Q1=B′의 산출 가치.

## 범위 외 (v1)
- 차트/스파크라인 등 고급 시각화(향후). 원격(비로컬) 운영. 다중 운영자. NL 매매에서 confirm 제거(안전상 비대상).

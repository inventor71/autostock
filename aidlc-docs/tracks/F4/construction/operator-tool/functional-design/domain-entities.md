# 도메인 엔티티 — Unit B `operator-tool` (F4, opencode 하드 fork)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit B · Functional Design · 2026-05-30._
_결정: Q1=B′(하드 fork), Q2=A, Q3=A, Q4=A, Q5=A, Q6=A–E, Q7=A._

> Unit B는 **운영자 콘솔**(opencode를 fork해 trader-agent 전용으로 리브랜딩). Unit A의 file-drop 계약을
> **소비/생산**하는 쪽이다. 새 도메인 개념은 대부분 *운영자 측*(입력 환원·확인·알림·패널 뷰모델)이며,
> 명령/이벤트 스키마(E7/E8)는 **Unit A가 소유**하고 Unit B가 준수한다.

## Unit A에서 소비/생산하는 계약 (재확인 — 변경 금지)
- **생산**: `SteeringCommand`(E7) → repo-root `steering/commands.jsonl`에 append. 필드(verb/args/`confirmed`/
  `token`/id/source="human") + 스키마는 Unit A 소유. Unit B는 이 스키마대로 **쓰기만**.
- **소비(읽기)**: `SteeringEvent`(E8) ← `steering/events.jsonl`(tail); `snapshot.json`(상태 뷰); agent journal/trace(read-only).
- **토큰**: env `STEERING_OPERATOR_TOKEN`(Q5=A)에서 읽어 매 명령에 부착. 파일/로그 금지.

## E-B1. `CommandDraft` (확인 전 환원 결과) — 운영자 측 핵심
사람 입력(자연어 또는 슬래시/키스트로크)을 **결정적으로 환원**한 매매/제어 의도. 아직 실행 전.

| 필드 | 설명 |
|---|---|
| `verb` | E7 verb(buy/sell/flatten/...) |
| `args` | symbol/size/unit/price/id 등(검증된) |
| `origin` | `nl`(LLM 제안) / `slash`(결정적 명령) / `keystroke`(TUI 직접) |
| `echo` | 사람이 읽을 1줄 해석(예 "SELL 100% AAPL @ market") |
| `risk_preview` | 확인 모달에 표시할 추정(현재가·노셔널·예상 stop) — **추정치 명시**(실행 시 데몬이 라이브 재조회) |

- **불변식**: `CommandDraft`는 **사람 확인 전에는 절대 `SteeringCommand`로 승격되지 않는다**(confirm 무결성).
  LLM(`origin=nl`)은 Draft까지만 만들고, 승격(토큰 부착+append)은 결정적 레이어가 사람 확인 후 수행.

## E-B2. `ConfirmationGate` (확인 상호작용)
파괴적/매매 명령의 확인. `[y/N]`(기본 N) 또는 파괴적(`/flatten all`,`/kill`)은 `CONFIRM` 키워드.
- 결정적 레이어(Go TUI 모달 또는 tool execute)가 소유 — **LLM이 우회/위조 불가**.
- 거부/타임아웃/빈입력 → no-op(fail-closed). 통과 시에만 `confirmed=True`로 승격.

## E-B3. `OutcomeWaiter` (요청–응답 상관)
보낸 명령의 `id`로 `events.jsonl`의 outcome 이벤트(`corr_id`)를 매칭해 결과 표시(체결/거부/no_order/error).
- 타임아웃 시 "결과 미수신" 경고(데몬 미동작/지연 가시화).

## E-B4. `NotificationInbox` (이벤트 피드, Q4=A)
`events.jsonl`을 백그라운드 tail해 받은 이벤트의 운영자 측 뷰. fill/pending/agent_question/reconcile/outcome.
- **push**: pending/fill/agent_question은 즉시 알림(토스트/패널). 전체 히스토리는 피드 패널.
- 마지막 표시 위치(오프셋)만 추적(이벤트는 Unit A가 append-only로 소유).

## E-B5. `SnapshotView` (읽기 뷰모델, Q3=A)
`snapshot.json`(+ journal)을 파싱한 패널 뷰모델: run_state(running/paused/halt), 포지션, 미체결 주문,
락/denied/pending 요약, market_open, 갱신 ts. **데몬 라운드트립 없음**(파일 읽기).

## E-B6. `AgentQuestionItem` (양방향, Q6-E)
`events.jsonl`의 `agent_question` 이벤트 → inbox 항목. 운영자가 `/answer <id> <text>`로 응답 →
`SteeringCommand(verb="answer")` 생산(토큰 부착) → Unit A가 `agent_answers.jsonl` 기록 + reconcile.

## E-B7. `OperatorVerb` 카탈로그 (Q6=A–E)
콘솔이 노출하는 명령(전부 E7 verb로 환원):
- 매매 A: buy/sell/flatten/flatten_all/stop · 라이프사이클 B: pause/resume/halt_entries/allow_entries/kill ·
  승인 C: pending/approve/reject/unlock · 조회 D(읽기): status/positions/orders/agent-trace/why ·
  컨텍스트 E: note/directive/answer.
- 매매·라이프사이클·승인·컨텍스트(쓰기) = 결정적 액션 레이어(E-B1/2). 조회 = 결정적 읽기(E-B5, 무해).

---

## 엔티티 관계 (텍스트)
```
사람 입력 ─┬ NL ──(LLM 제안)──> CommandDraft(origin=nl) ─┐
           ├ /slash, 키스트로크 ─> CommandDraft(origin=slash/keystroke) ─┤
           │                                                              ▼
           │                                          ConfirmationGate (결정적, 사람 y/CONFIRM)
           │                                                              ▼  (통과 시에만)
           │                              SteeringCommand(confirmed=True, token) ─> steering/commands.jsonl
           │                                                              │
           │                                              [Unit A 데몬: 검증→워커→게이트→실행]
           │                                                              ▼
           └ 조회 ─> SnapshotView(읽기)              events.jsonl ──tail──> NotificationInbox / OutcomeWaiter
                                                      agent_question 이벤트 ─> AgentQuestionItem ─(/answer)─> SteeringCommand
```
**불변식 요약:** 주문 경로에 LLM 권한 없음 — LLM은 `CommandDraft`까지만. 승격(토큰+append)은 결정적 레이어가
사람 확인 후에만. 최종 안전은 데몬측(Unit A). (상세 business-rules.md)

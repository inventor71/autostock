# 논리 컴포넌트 — Unit A `steering-core` (F4)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit A · NFR Design · 2026-05-29._
_재구현 모듈 분해(F2 `src/agent/steering/*`를 detached+file-drop로 새로 작성). 코드젠 단위 경계._

## 모듈 (신규/재구현, `src/agent/steering/`)

| 모듈 | 책임 | 비고 |
|---|---|---|
| `records.py` | pydantic: `SteeringCommand`(E7), `SteeringEvent`(E8), `AgentQuestion`(E9), `InterventionRecord`(E2), `Directive`(E6); `Decision.source`(E1)는 journal에 | PBT-02 round-trip |
| `jsonl.py` | **공유 torn-safe JSONL 리더 + 바이트오프셋 커서**(마지막 `\n`까지, 원자 커서 저장) | C-5; commands/decisions/agent_questions 재사용 |
| `channel.py` | file-drop **in**(commands 읽기·dedup·검증) / **out**(events append, snapshot 원자 게시) | BR-11/12, os.replace |
| `state.py` | `SteeringState`: RunState/HumanLock/PendingApproval/Directive 캐시 + `state_lock` + ET-date lazy 만료/sweep/영속 | BR-3/4/8, P1.4/1.5 |
| `bus.py` | `CommandQueue`(응급/normal 레인) + 단일 `CommandWorker` 스레드; 스케줄러 funnel enqueue API | P1.1, BR-7.1'/13 |
| `turns.py` | `TurnCoordinator`(turn_lock + in-flight 플래그 + `reconcile_turn`/`try_scheduled_turn`) + `ReconcileWorker`(트리거별 run_fn + 디바운스) | C-1/C-4, P1.2 |
| `commands.py` | verb 핸들러(거래/lifecycle/approval/unlock/cancel/stop/note/directive/answer) → executor/state/locks | BLM §1/§3.2 |
| `gate.py` | executor 승인 게이트: 에이전트 `Decision` 경로의 lock/denied/보호예외 판정(BR-4) | E4/E5 |
| `security.py` | PreToolUse 거부 스크립트(workspace 밖 deny) + settings.json 생성 + 토큰 발급/scrub 헬퍼 | BR-10, P5' |

## 기존 모듈 변경
| 파일 | 변경 |
|---|---|
| `src/agent/executor.py` | `_execute_one`→**공개 `execute_decision(Decision)`** 승격(커서 무접촉, market/off-hours 자체 판정); `.executor_state.json` 쓰기 **원자화**; 승인 게이트(`gate.py`) 연동 | 
| `src/agent/session.py` | spawn env에서 **운영자 토큰 scrub**; PreToolUse 훅 settings 경로 배선 |
| `src/trading/modes/agent.py` | 스케줄러 executor 호출을 **CommandWorker 큐로 funnel**(직접 호출 제거); file-drop 폴 잡·snapshot publisher 잡 기동; 콘솔 스레드 **제거**(detached) |
| `src/trading/scheduler.py` | `add_job`에 **`max_instances=1, coalesce=True` 명시** |
| `src/agent/journal.py` | `read_decisions`를 `jsonl.py` 공유 리더로 교체(스킵-드리프트 교정) |
| `src/agent/orchestrator.py` | reconcile 발화를 `TurnCoordinator`/`ReconcileWorker` 경유로 |

## 스레드 모델
```
[데몬 프로세스]
 ├ 스케줄러(APScheduler, max_instances=1/coalesce)
 │   ├ research/open/intraday/eod 잡 → TurnCoordinator.try_scheduled_turn() → (LLM은 turn_lock)
 │   │     └ executor 단계 → CommandQueue.enqueue(normal)   ← funnel(직접호출 금지)
 │   ├ file-drop 폴 잡(1–2s) → channel.read_commands → 검증/ dedup → CommandQueue.enqueue(lane)
 │   ├ snapshot publisher 잡(2–5s) → channel.write_snapshot(원자)
 │   └ ET 자정 sweep 잡 → state.sweep_expired
 ├ CommandWorker(단일) ── CommandQueue ── broker변이/executor커서/락스토어 (직렬, 응급 우선)
 │     └ 처리결과 → channel.append_event(outcome corr_id)
 ├ ReconcileWorker ── turn_lock(공유) ── orchestrator.run_reconcile(트리거별 run_fn)  (broker 미접촉)
 └ 메인 스레드: while True sleep (detached — 콘솔 없음). Ctrl-C→스케줄러 정지 후 종료.

[별도 프로세스] 운영자 도구(Unit B, opencode) → steering/commands.jsonl(append) / events·snapshot(read)  [토큰 보유]
[별도 프로세스] 에이전트 claude -p → workspace/(journal write, agent_questions write) [토큰 비보유, 훅으로 workspace 밖 차단]
```

## 검증 항목(코드젠에서 실측)
- PreToolUse 훅이 `claude -p`(cwd workspace)에서 로드되는 위치(`workspace/.claude/settings.json` vs `--settings`); `dontAsk`와 공존.
- 토큰이 에이전트 env에 부재; workspace 밖 Read/Write가 훅에 의해 deny.
- funnel 후 스케줄러-워커 경합 0(동일 심볼 동시 cancel/submit 없음); 커서 원자성.
- 동일 `session_id` `--resume` 2개 동시 불가(TurnCoordinator).
- file-drop torn write/재시작 멱등(id dedup); snapshot 원자 읽기(torn JSON 없음).

## 테스트 전략(요지 — Build&Test에서 확장)
- PBT(Hypothesis): records round-trip, 파서/검증/락 상태머신/커서 단조/토큰 검증.
- example: 미확인·토큰없음 거부 / kill·flatten_all / paused 스킵 / 보호 예외 / reconcile 실패 내성 / **권한 거부(에이전트 workspace 밖 차단 + 토큰위조 거부)** / funnel 경합.
- F2 안전 모델 동등성(BR-1..9 동작) 회귀 + 전체 기존 스위트 green.

# Code Generation 계획 (Part 1) — Unit A `steering-core` (F4)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit A · Code Generation · 2026-05-29._
_입력: Unit A Functional Design(BR/E) + NFR Design(P1~P6, logical-components) + /critic 반영 + opencode 조사._
_승인 시 Part 2 첫 동작 = **새 git worktree+branch 생성**(Q8=A, main 기준). 코드/worktree는 아직 없음._

## 원칙
- **계약·안전 우선**(헤드리스 CLI로 검증 가능), 변이 경로는 단일 워커로 funnel. 각 스텝은 **테스트 동반**.
- 라이브 main 무영향(worktree). 기존 스위트 + 신규 테스트 green 후에만 머지 후보.
- **신규 런타임 의존성 0**(stdlib + pydantic + 기존). 자연어/UI/confirm은 Unit B(이 유닛 범위 밖).

---

## 스텝 (체크박스 — 완료 시 즉시 [x])

### [x] Step 0 — worktree+branch
- [x] main 기준 새 worktree+branch(`feat/steering-core`) 생성 — `.claude/worktrees/steering-core`.

### [x] Step 1 — records + 공유 JSONL 리더 (foundation)
- [x] records.py (모든 레코드) + Decision.source 추가 — DONE.
- [x] jsonl.py: torn-safe 바이트오프셋 리더 + ByteCursor + atomic_write_text.
- [x] 테스트 test_steering_records.py — 10 passed.

### [x] Step 2 — SteeringState (상태머신 + ET-date)
- [x] state.py: RunState/HumanLock/PendingApproval/Directive + state_lock(RLock) + 원자 영속 + lazy 만료/sweep_expired + 카운터 재수화.
- [x] 테스트 test_steering_state.py — 11 passed (PBT-03 락 불변식 + ET-date 만료/리셋 + 재시작 복원 + 멱등 parking).

### [x] Step 3 — channel (file-drop in/out + snapshot)
- [x] channel.py: read_new_commands(torn-safe + confirmed+token(hmac) 검증 + 영속 processed-id dedup) / emit_outcome / append_event / publish_snapshot(원자).
- [x] 테스트 test_steering_channel.py — 7 passed (미확인/badtoken 거부 + 토큰 비기록 + dedup 영속 + torn + snapshot 원자).

### [x] Step 4 — executor 승인 게이트 + 단일-결정 실행 (주문 경로)
- [x] executor.py: `_execute_one`→공개 `execute_decision`(커서 무접촉; off-hours 큐는 호출자 책임으로 정리) + 커서 원자 쓰기. (외부 _execute_one 참조 0.)
- [x] gate.py: gate_agent_decision → execute/park/deny (BR-4.2/4.5/4.6; HOLD/ADJUST_STOP 면제).
- [x] 테스트 test_steering_gate.py 4 passed + executor 회귀 21 + **전체 232 green**.

### [x] Step 5 — bus (CommandQueue + 단일 CommandWorker)
- [x] bus.py: CommandBus(단일 워커 + PriorityQueue 응급/normal 레인 + submit/submit_and_wait/emergency_pending + WorkResult).
- [x] 테스트 test_steering_bus.py 4 passed (직렬화 max=1 + 응급 우선 + FIFO + 에러 후 워커 생존).

### [x] Step 6 — turns (TurnCoordinator + ReconcileWorker)
- [x] turns.py: TurnCoordinator(turn_lock + try_scheduled_turn skip-if-busy C-1 + reconcile_turn bounded+priority CQ-R1 best-effort) + ReconcileWorker(per-kind run_fn + debounce C-4).
- [x] 테스트 test_steering_turns.py 6 passed (in-flight 스킵 + reconcile 우선 yield + best-effort + 디바운스 coalesce + per-kind).

### [x] Step 7 — commands (verb 핸들러)
- [x] commands.py: CommandHandler 전 verb 디스패치(bus 워커) + build_human_buy(명시 $/sh + ATR bracket) + sell/flatten=execute_decision + off-hours 큐(channel) + outcome 이벤트 + InterventionRecord + reconcile 트리거.
- [x] 테스트 test_steering_commands.py 12 passed (build_human_buy 수학 + buy/sell/flatten/kill/approve 배선 + off-hours deferral + unknown-verb error). 전체 259 green.

### [x] Step 8 — security (권한 분리: 훅 + 토큰)
- [x] security.py: PreToolUse 거부 훅(stdlib, standalone) + write_agent_hook_settings + issue_token + scrub_agent_env.
- [x] session.py 토큰 scrub + 훅 settings 배선 — DONE (Step 9, 라이브 검증 PASS).
- [x] 테스트 test_steering_security.py 5 passed + standalone 스모크(inside rc0/outside rc2). **실 `claude -p` 검증 PASS ✅** — 훅이 workspace/.claude/settings.json에서 로드되어 workspace 밖 Read 차단(에이전트가 '보안 훅이 차단, operator token off-limits'라고 보고). BR-10.1 확정.

### [x] Step 9 — 배선 (데몬 통합)
- [x] `src/trading/modes/agent.py`: 스케줄러 executor 호출 **CommandWorker funnel**(직접 호출 제거); file-drop 폴 잡(1–2s)·snapshot publisher 잡(2–5s)·ET 자정 sweep 잡 기동; **in-process 콘솔 제거**(detached); agent_questions 폴→이벤트 push. — DONE
- [x] `src/trading/scheduler.py`: `add_job`에 **`max_instances=1, coalesce=True`**. — DONE
- [x] `src/agent/journal.py`: `read_decisions`→공유 `jsonl.py` 리더(스킵-드리프트 교정). — DONE
- [x] `src/agent/orchestrator.py`: reconcile 발화를 TurnCoordinator/ReconcileWorker 경유. — DONE
- [x] 테스트: 콘솔 부재에도 데몬 정상(no-regression); funnel 후 스케줄러-워커 단일 직렬. — 무회귀 확인

### [x] Step 10 — 통합·회귀·PBT (+ main.py 배선)
- [x] F2 안전 모델 동등성(BR-1..9 동작) 회귀; 권한 거부/토큰/torn/멱등 example; PBT 묶음; **전체 기존 스위트 green**. — 전체 271 green
- [x] (agentic path backtest 비대상.)

---

## 산출물 위치
- 코드: worktree의 `src/agent/steering/*` + 기존 파일 수정. 문서 요약: `aidlc-docs/construction/steering-core/code/code-summary.md`(Part 2 종료 시).
- **명령 채널: repo-root `steering/`**(workspace 밖, 권한 경계).

## 완료 기준
- 모든 스텝 [x] + 전체 테스트 green + 권한 거부/funnel/멱등/torn 테스트 green. Unit A는 **헤드리스 CLI로 운전 가능**(Unit B 전).
- 이후 Build&Test(유닛 통합) 및 Unit B(operator-tool) 진행.

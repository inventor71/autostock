# Unit A `steering-core` — Code Summary (F4)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit A · Code Generation 완료 · 2026-05-30._
_브랜치 `feat/steering-core` (main 기준 worktree). 7 커밋. 전체 스위트 271 green. **신규 런타임 의존성 0.**_

## 무엇을 만들었나
F2의 안전 모델을 **detached + file-drop**로 깨끗이 재구현한 데몬측 엔진. 별도 운영자 프로세스(Unit B,
opencode)가 repo-root `steering/`의 append-only 파일로만 데몬과 통신한다. 트레이딩 agent는 advisor-only로
유지되며 PreToolUse 훅으로 workspace 밖에 닿지 못한다(라이브 `claude -p`로 검증됨).

## 신규 모듈 (`src/agent/steering/`)
| 모듈 | 역할 |
|---|---|
| `records.py` | pydantic: SteeringCommand/Event/AgentQuestion/AgentAnswer/InterventionRecord/Directive/RunState/LockState/PendingApproval(전체 Decision 저장) |
| `jsonl.py` | torn-safe 바이트오프셋 리더 + ByteCursor + atomic_write_text(고유 temp) |
| `state.py` | SteeringState: RunState(ET-date 영속) + HumanLock 상태머신 + PendingApproval(멱등 parking) + Directive + lazy 만료/sweep, RLock |
| `channel.py` | file-drop in(confirmed+token hmac 검증, processed-id dedup) / events / atomic snapshot / off-hours 큐 / daily_reset |
| `bus.py` | CommandBus: 단일 워커 + 응급/normal 레인 + stop-drain + WorkResult |
| `turns.py` | TurnCoordinator(try_scheduled_turn skip-if-busy / reconcile_turn priority best-effort) + ReconcileWorker(per-kind debounce) |
| `gate.py` | gate_agent_decision: execute/park/deny (BR-4.6 보호 면제) |
| `commands.py` | CommandHandler 전 verb + build_human_buy(명시 $/sh + ATR bracket) |
| `security.py` | PreToolUse 거부 훅(stdlib, standalone) + 토큰 발급/scrub + 훅 settings 생성 |
| `runtime.py` | SteeringRuntime: 전체 조립 + 데몬 잡(poll/snapshot/sweep/offhours-drain/agent-question push) |

## 기존 파일 수정
- `executor.py`: `_execute_one`→공개 `execute_decision`(커서 무접촉) + 커서 원자 쓰기.
- `journal.py`: `Decision.source` 추가; `read_decisions`→공유 torn-safe 리더.
- `session.py`: spawn env 토큰 scrub(BR-10.2).
- `orchestrator.py`: `run_reconcile` 추가.
- `scheduler.py`: `max_instances=1, coalesce=True` 명시 + `add_seconds_job`.
- `modes/agent.py`: optional `steering=` — executor funnel(단일 워커), 턴 coordinator 경유, paused 게이트(보호 청산만), off-hours drain, 스티어링 잡, start/stop.
- `main.py`: `--steering` 플래그 + run_agent가 SteeringRuntime 구성.

## 안전/품질
- **권한 분리(BR-10) 라이브 검증 PASS**: 헤드리스 `claude -p`가 PreToolUse 훅을 로드해 workspace 밖 Read 차단.
- 동시성: 단일 CommandWorker(broker 변이+커서) + turn_lock(LLM 세션). 스케줄러 executor도 funnel.
- 멱등/torn-safe: 바이트오프셋 리더, command id dedup, 원자 쓰기, off-hours 큐.
- `/critic` 코드 검토 8건 반영(stop-drain, ET-date 일관, reconcile priority, 토큰 비구조 정정 등).
- **NFR-8 무회귀**: `--steering` 없으면 기존 동작 그대로(전체 271 green).

## 테스트 (~78 신규)
`tests/test_steering_{records,state,channel,bus,turns,gate,commands,security,runtime}.py` — PBT(레코드/락/커서) +
example(안전경로·권한거부·off-hours·approve·funnel·snapshot) + 런타임 통합(poll→bus→handler) + 스탠드얼론 훅 스모크.

## 검증된 사실 (비자명)
헤드리스 `claude -p`는 `workspace/.claude/settings.json`의 PreToolUse 훅을 로드하며 exit-2로 도구 호출을
hard-block한다(`--permission-mode dontAsk`여도). → BR-10.1 권한 경계가 구조적으로 성립.

## 남은 것 (Unit A 범위 밖)
- **Unit B `operator-tool`**(opencode rebrand): NL→verb 환원 + confirm + 토큰 부착 + 이벤트 tail + agent-trace.
- **Build & Test 스테이지**(전 유닛 후): 통합/성능/보안 테스트 지시 문서.
- F3(intraday)가 이 엔진 위로 rebase.

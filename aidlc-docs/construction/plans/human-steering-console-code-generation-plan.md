# 코드 생성 계획 (Part 1) — human-steering-console

_AI-DLC 트랙 F2 · CONSTRUCTION · Code Generation · 2026-05-29. 브라운필드(기존 파일 수정 우선)._
_근거: requirements / functional-design(domain-entities·business-logic-model·business-rules·frontend-components) /
nfr-design(patterns·logical-components) — 모두 승인됨. 이 계획이 코드 생성의 단일 진실원._

> **승인 후 Part 2 진행.** Part 2의 **0번째 행동 = git worktree+브랜치 생성**(Q8=A) 후 그 안에서 단계별 코드 작성.
> 코드는 워크스페이스 루트(`src/…`, `main.py`, `pyproject.toml`, `scripts/`)에, 코드 요약 md만 `aidlc-docs/.../code/`.

## 대상 / 의존성 / 추적
- **신규 런타임 의존성:** `prompt_toolkit` 1개(`rich`·`hypothesis`는 기존). SECURITY-10: 핀.
- **신규 패키지:** `src/agent/steering/`. **수정:** `journal.py`·`executor.py`·`orchestrator.py`·`prompts.py`·
  `trading/modes/agent.py`·`main.py`·`pyproject.toml`·`scripts/monitor.sh`.
- **스토리 대체 추적:** User Stories는 SKIP이므로 FR-1..8 / BR-1..9 / CQ-* / 검토#1..11 로 추적.

---

## 단계 (순차, 각 단계 끝에 테스트)

- [ ] **Step 1 — 의존성 + 패키지 스캐폴딩**
  - 수정 `pyproject.toml`: `prompt_toolkit>=3.0` 핀 추가(SECURITY-10). 생성 `src/agent/steering/__init__.py`.
  - 추적: NFR tech-stack, SECURITY-10.

- [ ] **Step 2 — 도메인 레코드 + `Decision.source`**
  - 수정 `src/agent/journal.py`: `Decision.source: Literal["agent","human"]="agent"`(하위호환). **torn-line 방어(검토 #8)**:
    `read_decisions`가 개행 미종료 마지막 청크를 **파싱 전 제거**; executor 커서는 **완전한 물리적 줄 수** 기준(현 `len(parsed)`의 skip 드리프트 제거).
  - 생성 `src/agent/steering/records.py`: `InterventionRecord`·`PendingApproval`·`Directive`·`LockState`(pydantic).
  - 테스트 `tests/test_steering_records.py`: 직렬화 라운드트립(**PBT-02**), torn-line skip(예제).
  - 추적: E1/E2/E5/E6, 검토#8.

- [ ] **Step 3 — SteeringState + 스토어(영속·lazy 만료·id 재수화)**
  - 생성 `src/agent/steering/state.py`: `RunState`(`run_state.json`, ET-date 영속·CQ-D1=A), `HumanLockStore`(`human_locks.json`),
    `PendingApprovalStore`(`pending_approvals.jsonl`), `DirectiveStore`(`directives.jsonl`), `InterventionLog`(`human_directives.jsonl`, append-only),
    snapshot 캐시; `state_lock`; **접근마다 lazy ET-date 만료**; **id 재수화=max+1**.
  - 테스트 `tests/test_steering_state.py`: 락 상태머신 불변식(**PBT-03**: reject_count 단조·denied⇔≥2·approve 제거), ET-date 만료,
    id 재수화, run_state 복원. **로드 시점 날짜 체크(검토 #7)**: 날짜 D 저장 → D+1 프로세스 시작 → running(자정 교차 크래시 재시작) 명시 테스트.
  - 추적: E3/E4, BR-3/BR-4, 검토#2/#3/#9(CQ-D1=A).

- [ ] **Step 4 — 명령 파서(순수)**
  - 생성 `src/agent/steering/commands.py`(Command dataclasses), `src/agent/steering/parser.py`(슬래시 파싱, 크기 단위 `$`/`sh`/`%`, 거부+사유).
  - 테스트 `tests/test_steering_parser.py`: 예제 + Hypothesis 불변식(**PBT-03**: 유효 크기 없는 거래 미산출; `%`→(0,1]; trade→source=human).
  - 추적: business-logic-model §1/§2, LC6.

- [ ] **Step 5 — Executor 확장(게이팅·직접 실행·멱등 parking·점진 커서)**
  - 수정 `src/agent/executor.py`: `SteeringState` 선택 주입; `execute_pending` 게이팅(locked→PendingApproval 멱등 생성/denied→자동 거부+피드백/보호 예외);
    `execute_decision(decision)` 사람 거래 직접 경로(커서 무관); **폐장 시 `pending_human_trades` 큐에 보류**(CQ-R2=A);
    결정 단위 점진 커서; market-open은 스냅샷 우선.
  - 테스트 `tests/test_steering_executor.py`(SimulatedBroker): 게이팅 3분기, 멱등 parking(중간 실패 재실행), execute_decision, 보호 예외.
  - 추적: BR-2/BR-4/BR-5, 검토#4/#7/#8.

- [ ] **Step 6 — CommandBus(2-레인 큐+워커)+lifecycle**
  - 생성 `src/agent/steering/bus.py`: emergency/normal 2-레인, 단일 워커, 핸들러(trade/flatten/flatten all/kill/stop/cancel/approve/reject/unlock/pause/resume/halt/allow);
    응급 선점 + 다심볼 배치 심볼-사이 양보(yield); 결과 future.
  - 테스트 `tests/test_steering_bus.py`: 직렬화, 응급 선점 순서, lifecycle 게이팅(pause/halt no-op).
    **통합(검토 #8):** `execute_pending`을 다심볼 배치 중간에 응급 명령으로 인터럽트 → **중복 park 없음·커서 드리프트 없음** 확인
    (Step5 멱등 parking이 emergency-yield 재진입 경로에서도 성립하는지; 이 경로는 Step6에서 처음 생김).
  - 추적: P1, BR-1/BR-3/BR-5/BR-7, 검토#1/#8.

- [ ] **Step 7 — TurnCoordinator + ReconcileWorker + 프롬프트**
  - 생성 `src/agent/steering/turns.py`(turn_lock 코디네이터, ReconcileWorker: 디바운스·`acquire(blocking=False)` 양보·스킵 로깅).
  - 수정 `src/agent/orchestrator.py`: `run_reconcile(context)` 턴; `_run`이 turn_lock 사용. 수정 `src/agent/prompts.py`: `reconcile_prompt` + directive/사람개입 맥락을 morning/intraday/eod에 주입.
  - 테스트 `tests/test_steering_reconcile.py`: 디바운스/coalesce, 비블로킹 양보, best-effort 실패 내성, 에이전트 피드백 내용.
  - 추적: BR-6, FR-6/FR-7, 검토#5.

- [ ] **Step 8 — SteeringConsole(prompt_toolkit + rich) + Notifier**
  - 생성 `src/agent/steering/console.py`: PromptSession, Completer(명령+심볼), 하단 툴바, 확인 흐름(`[y/N]`+`CONFIRM`), rich 출력/테이블,
    Notifier(patch_stdout 비동기 알림), `/help`·에러 메시지; 비-TTY 자동 비활성화; 콘솔 부착 시 loguru stdout 싱크 제거.
  - 테스트 `tests/test_steering_console.py`: 확인 흐름·CONFIRM·명령 디스패치·에러 매핑(입력/브로커 목). #11(버퍼 보존) 수동/통합 검증 표기.
  - 추적: frontend-components C1–C11, BR-1/BR-8, 검토#6/#11.

- [ ] **Step 9 — main.py / modes/agent 통합**
  - 수정 `src/trading/modes/agent.py`: SteeringState/CommandBus/TurnCoordinator/ReconcileWorker/SteeringConsole 조립; 스케줄러 잡 재배선
    (LLM→turn_lock, executor 단계→CommandBus; market-open→스냅샷); **ET 자정 sweep 잡** 등록; **market-open 잡이
    `pending_human_trades` 드레인**(CQ-R2=A); 메인 스레드 TTY면 콘솔, 아니면 sleep-wait; quit→콘솔만, Ctrl-C→데몬.
  - 수정 `src/trading/scheduler.py`(검토 #4): `BackgroundScheduler(job_defaults={"max_instances":1,"coalesce":True})` **명시**(기존 암묵 기본값 → 명시).
  - 수정 `main.py`: `run_agent` 배선 + 콘솔 enable(TTY) + 설정.
  - 테스트 `tests/test_steering_integration.py`(SimulatedBroker): lifecycle 게이팅 e2e, 사람 거래 게이트 통과, sweep 만료.
  - 추적: LC9, FR-1/FR-5, 검토#2/#7.

- [ ] **Step 10 — monitor.sh 패널 + 코드 요약 문서**
  - 수정 `scripts/monitor.sh`: 데몬+콘솔 패널 추가(CQ5=A).
  - 생성 `aidlc-docs/construction/human-steering-console/code/code-summary.md`(생성/수정 파일·매핑 요약).
  - 추적: CQ5.

- [ ] **Step 11 — 전체 회귀 + PBT 시드**
  - `pytest` 전체(기존 196 + 신규) 그린; Hypothesis 시드 로깅(PBT-08). (실제 실행/검증은 Build & Test 단계.)
  - 추적: NFR-5(무회귀), PBT-08.

---

## 컴플라이언스 게이트(코드 생성 시 적용)
- **SECURITY-03**(로그 redaction)/**10**(prompt_toolkit 핀)/**11**(스티어링·주문 분리, 방어심층, CONFIRM)/**13**(append-only·pydantic 안전)/**15**(fail-closed·스레드 격리·finally).
- **PBT**(부분): Step2 라운드트립(02), Step3/4 불변식(03), Step3 생성기·시드(07/08), 예제 보완(10). 프레임워크 Hypothesis(09).

## 범위 메모
- `src/backtest/engine.py`의 4번째 폴드-청산 유사 지점은 본 유닛 범위 밖(F1/이전 트랙에서 다룸).
- NL→거래 파싱, 학습 루프, textual 풀 TUI는 v1 범위 밖(요구사항 §5 deferred).

# F4 — Claude-Code-native Steering Console (F2 프론트엔드 교체) — 요구사항

_상태: Requirements Analysis 완료(승인 대기). Brownfield, AI-DLC 트랙 F4._
_근거: `steering-console-redesign-questions.md`(Q1–Q9) + `steering-console-redesign-clarification-questions.md`(Clarif-1/2), 2026-05-29 확정._

---

## 1. 의도 분석 (Intent Analysis)

| 항목 | 값 |
|---|---|
| **요청 유형** | 기존 기능(F2)의 대규모 재설계 — 프론트엔드 교체 + 통신 모델 변경 |
| **범위** | Multiple components (운영자 콘솔 신규(opencode fork), file-drop 명령 채널, 데몬측 안전 엔진 재구현, agent journal/이벤트 채널, F3 재정렬) |
| **복잡도** | Complex (라이브 주문 경로 + 동시성 + 별도 프로세스 IPC + 권한 분리 + 외부 TUI fork) |
| **요구사항 깊이** | Comprehensive-leaning |

**요청(축약, 사용자 의도):** 개발 중인 F2 human-steering-console(`prompt_toolkit` REPL)을 **별도의
대화형 운영자 세션**으로 교체한다. 그 세션에 다양한 custom command를 등록하고, **opencode.ai를
customize한 버전**을 운영자 TUI로 쓴다. 목적은 (1) **자연어 명령 지원이 더 쉬움**, (2) 돌아가는
**intraday/research agent와 더 밀접한 communication**.

---

## 2. 코드 근거 / 통합 표면 (2026-05-29 확인)

- PM 트레이딩 **agent 자체가 이미 Claude Code 세션**이다 — `AgentSession`(`src/agent/session.py`)이
  `claude -p --resume`를 매 ET 거래일 세션으로 돌리고(tools 활성, `workspace/`에서, **advisor-only**),
  journal에만 쓴다. 주문은 넣지 않는다.
- 유일한 주문 경로: `agent/executor.DecisionExecutor` → `RiskManager`(bracket/OCO) → `Broker`,
  cursor-idempotent(`.executor_state.json`).
- 진실의 원천: 파일 기반 `agent/journal.Journal`(`workspace/`).
- F2(브랜치 `feat/human-steering-console`, 13 커밋, 268 테스트, **머지 안 됨**)는 이미
  **데몬측 안전 엔진**(`src/agent/steering/{bus,commands,parser,records,state,turns}.py`) +
  **프론트엔드**(`steering/console.py`, prompt_toolkit)로 분리돼 있다. F2 NFR-1이 단일 직렬화
  command path를 설계하며 "headless용 **file-drop front-end**를 같은 큐로 거의 공짜로 붙일 수 있다"고
  명시 — F4가 그 file-drop front-end를 실제로 구현한다.
- F3(intraday 재설계)는 F2의 `TurnCoordinator`/`ReconcileWorker`/`SteeringState`를 재사용하도록 설계됨
  → F4가 그 엔진을 **재구현**하므로 F3는 F4 엔진 위로 재정렬된다(§9).

---

## 3. 확정 결정 (질문 답변)

| # | 결정 | 답 |
|---|---|---|
| Q1 | F2 **데몬측 엔진**의 처리 | C→Clarif-1=A로 정밀화 |
| Clarif-1 | "폐기"의 범위 = **브랜치 코드 + `console.py` 프론트엔드 + parser 폐기**, 데몬측 **안전 아키텍처**(직렬화 command path, executor→RiskManager→Broker 게이트, reconcile, approval 게이트, SteeringState)는 **개념 채택 + Claude-Code-native·file-drop로 깨끗이 재구현** | **A** |
| Q2 | 운영자 콘솔 프론트엔드 = **opencode.ai를 베이스로 trader-agent 전용 도구로 리브랜딩/전유**(업스트림 추적 fork가 아니라 우리 도구로 소유) | B(정제) |
| Q3 | IPC = **file-drop 큐**(운영자 명령을 JSONL/파일에 append → 데몬 단일 워커가 같은 안전 게이트로 처리) | A |
| Q4 | 자연어 매매 = **허용 + echo·confirm 게이트**(LLM은 *제안*만, `y`/`CONFIRM` 확인해야 실행) | B |
| Q5 | agent communication 범위 = **읽기(A) + 이벤트 푸시(C) + 양방향 질의(D)** v1, **쓰기/조종(B) 일부** v1(지시/가이드 주입) + 추후 확장 | A,C,D,B(부분) |
| Q6 | 운영자 세션 ↔ agent 세션 = **완전 detached**(독립 프로세스, 파일/IPC로만 통신) | A |
| Q7 | F2 브랜치/F3 = **F2 브랜치 폐기**, F3 설계도 F4 기준 재정렬(데몬 엔진은 Clarif-1=A로 재구현되어 존속) | C |
| Q8 | 운영자 command 세트 = **매매(A)+라이프사이클(B)+승인게이트(C)+조회(D)+컨텍스트주입(E)** 전부 + **하드 제약: 운영자 command 권한은 research/intraday agent 세션에서 절대 접근 불가** | A–E |
| Q9 | 확장 = 프로젝트 기본 유지(Security Baseline Enabled; PBT Partial/Hypothesis) | A |
| Clarif-2 | 순서 = **opencode fork를 v1부터 1급 deliverable**로 계약+TUI 동시 구축 | B |

---

## 4. 설계 방향 (아키텍처)

```
+---------------------------+        file-drop (append-only JSONL)        +-----------------------------+
|  운영자 콘솔 (opencode fork)|  --- commands/{cmd}.jsonl, confirm 후 --->  |  데몬 (main.py --mode agent)|
|  - 자연어 + custom command  |                                            |  단일 CommandWorker          |
|  - LLM은 *제안*만           |  <--- events/notifications (이벤트 푸시) --- |  → executor→RiskManager→     |
|  - 권한: 운영자 전용        |  <--- agent journal/trace (읽기) --------- |    Broker (유일 주문 경로)   |
+---------------------------+  <--- agent 질문(양방향 질의 D) ----------- |  + reconcile/approval 게이트 |
                                                                          |  + SteeringState             |
                                                                          +--------------+--------------+
                                                                                         |
                                              advisor-only (주문 권한 없음, 운영자 채널 접근 불가)
                                                                                         v
                                                              research / intraday agent (claude -p 세션, journal write)
```

- **세 개의 LLM 컨텍스트**가 공존한다: ① research agent, ② intraday/PM agent(②와 ①은 같은 일일
  세션 계열), ③ **운영자 콘솔(opencode fork)**. ①②는 advisor-only, ③만 command 권한을 가진다.
- **운영자 콘솔(opencode fork)**: 자연어를 받아 LLM이 의도를 해석하되, 매매/라이프사이클 같은
  변형 명령은 **deterministic command 1줄로 환원해 echo → 사람이 `y`/`CONFIRM` 확인 → file-drop에
  append**한다(Q4=B). 즉 LLM은 번역·제안기이고, 실행 권한은 confirm + 데몬 게이트가 통제.
- **file-drop 계약(Q3=A)**: 운영자 콘솔은 데몬을 *직접* 건드리지 않는다. append-only JSONL에 명령을
  쓰고, 데몬의 **단일 CommandWorker**가 이를 읽어 F2와 동일한 직렬화 안전 게이트로 처리한다. 읽기/
  이벤트도 파일 기반(데몬이 events·notifications를 파일로 내보냄; 운영자 콘솔이 tail).
- **detached(Q6=A)**: 운영자 콘솔과 데몬은 독립 프로세스. 데몬은 foreground/tmux 없이도 동작
  (F2 요구사항 §6의 attached 가정 해소). 콘솔이 죽어도 데몬은 정상 트레이딩.
- **데몬측 안전 엔진은 재구현(Clarif-1=A)**하되 F2의 안전 모델을 그대로 따른다. 재구현이므로 F3의
  적대검토 발견(C-1..C-8: TurnCoordinator skip-if-busy, snapshot 페이로드, JSONL reader/cursor 등)을
  **처음부터 반영**할 기회다(§9).

---

## 5. 기능 요구사항 (Functional Requirements)

### FR-1 — 운영자 콘솔 (opencode 베이스 리브랜딩) [Q2=B, Q6=A]
- opencode.ai를 **베이스로 가져와 trader-agent 전용 도구로 리브랜딩/전유**한 대화형 TUI가 운영자
  인터페이스가 된다. 목표는 "업스트림을 따라가는 fork 유지보수"가 아니라 **우리 도구로 소유**(필요한
  부분만 남기고 트레이딩-ops에 맞게 개조; 업스트림 동기화 의무 없음).
- 데몬과 **독립 프로세스**로 실행. 통신은 file-drop(FR-3) + 파일 기반 읽기/이벤트(FR-5/FR-6)만.
- 콘솔이 종료/크래시해도 데몬 트레이딩은 무영향(fail-safe).

### FR-2 — Custom command 세트 (v1) [Q8=A–E]
운영자 콘솔에 등록할 명령(모두 file-drop 또는 읽기로 환원):
- **매매(A):** `buy/sell/flatten/stop` — Q4=B 정책(자연어 해석 → deterministic 1줄 echo → confirm).
- **라이프사이클(B):** `pause/resume/halt-entries/allow-entries/kill`(kill·flatten all은 `CONFIRM`).
- **승인 게이트(C):** `pending/approve/reject/unlock`(F2 FR-8 human-approval 게이트 계승).
- **조회(D):** `status/positions/orders/agent-trace/why/journal 요약`(읽기 전용, file-drop 불필요).
- **컨텍스트 주입(E):** `note/directive` + reconcile 트리거.

### FR-3 — file-drop 명령 채널 + 데몬측 안전 게이트 [Q3=A, Clarif-1=A]
- 운영자 명령은 **append-only JSONL**(예: `workspace/steering/commands.jsonl`)에 기록된다. 레코드는
  pydantic 타입(SECURITY-13), `source="human"`, confirm 완료 표시 포함.
- 데몬의 **단일 CommandWorker** 스레드만 이를 읽어 처리: torn-line 가드 + 완전 라인만 커서 진행
  (F2/journal 규율). 매매는 **기존 `DecisionExecutor`→`RiskManager`→`Broker`** 게이트로(제2 주문
  경로 없음). 모든 broker mutation·executor cursor 접근은 이 단일 워커에 직렬화(F2 NFR-1 불변식).
- off-hours 명령은 큐에 보관 후 장 개장 잡이 드레인(F2 CQ-R2 계승).

### FR-4 — agent 인지: reconcile turn + 직렬화 [Q5=B 부분]
- 운영자 매매/지시 후 데몬은 **out-of-band reconcile turn**을 발화(best-effort): agent가 라이브
  broker 상태 + 신규 directive를 재독해 journal/per-symbol thesis/protection을 갱신해 drift 방지.
- 모든 LLM 발화(스케줄 + reconcile + 향후 F3 wake)는 **단일 turn_lock** 경유(두 `claude --resume`
  겹침 방지). reconcile는 다음 스케줄 turn보다 우선.

### FR-5 — agent 읽기 (운영자→agent 상태 가시성) [Q5=A]
- 운영자 콘솔은 agent의 journal/theses/turn trace를 조회할 수 있다(이미 `scripts/agent_trace.py` +
  `/agent-trace` 존재 → custom command로 노출). 읽기 전용, file-drop 불필요.

### FR-6 — 이벤트 푸시 [Q5=C]
- 체결/결정/승인대기(PendingApproval)/agent 질문 발생 시 데몬이 **이벤트를 파일로 내보내고**
  (예: `workspace/steering/events.jsonl`), 운영자 콘솔이 tail해 알림으로 표시. (F2 in-process
  `notify()`/patch_stdout를 파일-이벤트로 대체 — detached 구조의 필연.)

### FR-7 — 양방향 질의 [Q5=D]
- agent가 사람에게 질문을 남길 수 있다(예 "META 손절 후 재진입?"): agent가 질문 채널
  (예 `workspace/agent_questions.jsonl`)에 append → FR-6 이벤트로 운영자에 푸시 → 운영자가
  `directive`/전용 응답 명령으로 답 → FR-3 채널 → reconcile turn에서 agent가 반영.
- v1은 **경량 구현**(질문 적재 + 응답 directive 라우팅). 풍부한 대화형 협상은 추후.

### FR-8 — Human-approval 게이트 계승 [Q8=C]
- 사람이 매매한 심볼은 **human-locked**: agent의 *재량* BUY/SELL은 PendingApproval로 보류
  (`pending/approve/reject`), 승인→실행+unlock, 2회 거부→당일 denied(사람 재매매 시 reset).
  보호주문/risk-exit/`ADJUST_STOP`/`HOLD`+stop은 게이트 면제(전 포지션 보호 불변식). ET-date 스코프.
  (F2 FR-8 설계를 재구현 엔진에서 그대로 계승.)

---

## 6. 비기능 요구사항 (Non-Functional Requirements)

### NFR-1 — 권한 분리 (이번 트랙의 핵심 보안 제약) [Q8 하드 제약]
- **운영자 콘솔의 command 권한은 research/intraday/PM agent 세션에서 절대 접근 불가**여야 한다.
  - agent 세션은 advisor-only: `AgentSession.DEFAULT_ALLOWED_TOOLS`(Read/Write/Edit/Glob/Grep/Web +
    `Bash(python -m src.agent.tools:*)` 읽기 전용 시장 CLI)로 제한, 주문 권한 없음.
  - **agent의 cwd는 `workspace/`**, file-drop **명령 채널은 agent가 쓰기 권한 없는 위치/도구**여야
    한다. agent의 allowedTools/Bash 화이트리스트에 운영자 명령 CLI·주문 enqueue 경로를 **포함 금지**.
  - 즉 "agent가 자기 자신에게 매매를 지시"하는 권한 상승이 구조적으로 불가능해야 한다(SECURITY-11
    secure design, fail-closed).
- 검증: agent 세션에서 명령 채널 write/주문 enqueue 시도가 거부됨을 테스트로 고정.

### NFR-2 — 동시성 & 직렬화 (재구현되어도 F2 불변식 유지) [Clarif-1=A]
- broker mutation + executor cursor 접근은 **단일 CommandWorker**에만; LLM 발화는 **단일 turn_lock**에.
- 운영자 콘솔(별도 프로세스)은 데몬을 직접 호출하지 않고 file-drop에 append만 → 프로세스 간 경합은
  append-only + 단일 reader 커서로 회피(torn-line 가드).

### NFR-3 — 일관성 / orphan 방지
- 강제 청산은 잔존 보호주문을 남기지 않는다(executor reconciliation), cursor 정합 유지 → agent 다음
  turn 혼선 없음(`DecisionExecutor` 경유로 충족).

### NFR-4 — fault isolation
- 운영자 콘솔 크래시·파싱 실패·reconcile 실패가 데몬을 죽이지 않는다(예외 로깅 후 계속, F2 패턴).

### NFR-5 — 자연어 매매 안전 [Q4=B]
- LLM은 매매를 *제안*만; 실제 enqueue 전 **deterministic 1줄 환원 + echo + `y`/`CONFIRM` 확인**.
  미확인/타임아웃/파싱불가 = no-op(fail-closed, SECURITY-15). 확인 게이트 + RiskManager 게이트가
  비결정성에 대한 이중 방어선.

### NFR-6 — 보안 (확장 enforced, Q9=A)
- **SECURITY-03**: 명령/이벤트/로그에 비밀·API 키 금지(심볼/수량/가격/사용자 텍스트만).
- **SECURITY-10**: opencode fork 및 신규 런타임 의존성 버전 핀(`pyproject.toml`/fork lockfile).
- **SECURITY-11**: 권한 분리(NFR-1) + 주문 로직은 `DecisionExecutor`/`RiskManager`에 고립.
- **SECURITY-13**: 명령/디렉티브 레코드는 pydantic 안전 역직렬화 + append-only 감사 로그(actor/action/ts/outcome).
- **SECURITY-15**: fail-closed(미확인·미파싱·타임아웃 no-op; 락 finally 해제; 데몬 무중단).
- 그 외(전송/저장 암호화, 웹 헤더, 네트워크 authN/Z)는 N/A — 로컬 단일 운영자(단, FR-1의 별도
  프로세스 IPC는 **로컬 파일**이므로 새 네트워크 표면 없음).

### NFR-7 — 테스트 & PBT (partial, Q9=A)
- Hypothesis(PBT-09). PBT-02 명령/디렉티브 레코드 round-trip; PBT-03 파서/환원 불변식(매매는 항상
  `source="human"`; 미인식 입력은 실행 산출 없음; `sell_pct ∈ (0,1]`); PBT-07/08 생성기·shrinking.
  example 테스트로 안전경로 고정(confirm 게이트, kill, paused skip, reconcile 실패 내성, 권한 거부).

### NFR-8 — 회귀 없음
- 운영자 콘솔 미사용/미연결 시 `main.py --mode agent`는 현재와 동일 동작. 기존 회귀 + 신규 테스트 통과 후 머지.

### NFR-9 — opencode 베이스 도구 운영 [Q2=B 정제]
- opencode를 **하드 포크/벤더링해 우리 도구로 소유**(별도 리포 vs 서브트리/벤더링은 설계 단계 결정).
  **업스트림 추적 의무 없음** — 가져온 시점을 baseline으로 고정해 트레이딩-ops에 맞게 리브랜딩·개조한다.
  라이선스 준수 + 의존성 버전 핀(SECURITY-10)은 유지. 자연어→command 매핑은 이 도구의 custom
  tool/command로 구현하되 **실행은 file-drop 계약만** 통과.

---

## 7. 스코프 / 빌드 단위 / 순서 [Clarif-2=B]

- **opencode fork를 v1부터 1급 deliverable**로 — file-drop 계약 + 데몬 엔진 + opencode TUI를 함께.
- **단위 분해(설계 단계에서 확정 예정, 잠정):**
  1. **데몬측 안전 엔진 재구현** — file-drop 명령 채널(records/parser-validator/reader+cursor) +
     단일 CommandWorker + executor 안전 게이트 + reconcile/turn_lock + approval 게이트 + SteeringState.
     (F2 안전 모델 + F3 critic 발견 선반영.) 헤드리스 CLI로 검증 가능.
  2. **이벤트/읽기 채널** — events.jsonl 내보내기, agent 질문 채널, agent-trace 노출.
  3. **opencode fork** — 트레이딩-ops TUI: custom command, 자연어→deterministic 환원+confirm, 이벤트 tail.
  4. **권한 분리 enforcement + 테스트**(NFR-1) + 전체 회귀 + PBT.
- 새 git worktree+branch에서 구현, 라이브 main은 머지 전 무영향.

---

## 8. F2 브랜치 처리 [Q7=C, Clarif-1=A]

- `feat/human-steering-console` 브랜치는 **deliverable로 폐기**(머지하지 않음). 단, 그 안의 **안전
  모델·테스트·도메인 레코드 설계는 참조 자산**으로 활용해 F4 엔진을 재구현(코드 살라미 머지가 아니라
  fresh 구현, 같은 안전 모델).
- F2의 설계 문서(`aidlc-docs/construction/human-steering-console/`)는 재구현 시 안전요구 체크리스트로 참조.

## 9. F3(Intraday 재설계) 재정렬 영향 [Q7=C]

- F3는 F2의 `TurnCoordinator`/`ReconcileWorker`/`SteeringState`/`CommandBus`를 재사용하도록 설계됨.
  F4가 이 엔진을 **재구현**하므로, F3는 **F4의 재구현 엔진 위로 재정렬**된다(인터페이스 재지정).
- 이득: F3 적대검토 발견 **C-1(skip-if-busy=TurnCoordinator 수정), C-3(snapshot 페이로드 확장),
  C-4(트리거별 run_fn), C-5(공유 JSONL reader+cursor), C-7(게이트 입력 분리)** 등을 F4 엔진에
  **처음부터 내장** → F3는 "기존 primitive 수정"이 아니라 "이미 일반화된 엔진에 트리거 소스 추가"가 됨.
- F3 설계 문서/state는 F4 승인 후 baseline 재지정(별도 후속 작업).

## 10. 범위 외 (v1) / 추후
- 풍부한 양방향 agent↔사람 협상 대화(FR-7은 경량). 
- 운영자 개입으로부터의 능동 학습(EOD 반영) — F2 계승하여 deferred.
- 원격(비로컬) 운영 — file-drop은 로컬 전제. 원격은 별도 보안 설계 필요.
- 자연어→매매에서 confirm 제거(완전 자동) — 안전상 비대상.

## 11. 확장 컴플라이언스 요약 (Requirements 단계)
- **Security Baseline(enforced):** SECURITY-03/10/11/13/15 적용(NFR-1/6). 권한 분리(SECURITY-11)가
  이번 트랙의 추가 강조점. 그 외 N/A(로컬, 새 네트워크 표면 없음). 블로킹 없음.
- **Property-Based Testing(partial):** PBT-02/03/07/08/09(NFR-7). 블로킹 없음.

## 12. 리스크
- **High–Medium.** (1) 데몬측 안전 엔진 **재구현**은 라이브 주문 경로를 새로 검증해야 함(테스트로
  F2 안전 모델 동등성 고정 필요). (2) **opencode 베이스 리브랜딩**은 외부 코드베이스를
  소유·개조하는 부담(F2가 피하려던 "콘솔 직접 구축"의 더 큰 버전) + 라이선스/핀. 단 업스트림 추적
  의무를 지지 않으므로(하드 포크) 지속적 merge 부담은 없음 — 가져온 baseline을 고정해 우리 코드로 관리. (3) 별도 프로세스 IPC·권한
  분리는 새 실패 모드. 완화: worktree 격리(쉬운 롤백), 헤드리스 CLI로 계약 우선 검증, 권한 거부
  테스트, F3 critic 발견 선반영.

## 13. 요약
F2의 prompt_toolkit REPL·parser·브랜치는 폐기하고, **F2의 데몬측 안전 모델은 보존**해 Claude-Code-
native + **file-drop**로 깨끗이 재구현한다. 운영자 인터페이스는 **opencode를 베이스로 trader-agent
전용 도구로 리브랜딩한 별도 프로세스 TUI**(detached, 업스트림 추적 의무 없는 하드 포크)로, 자연어를 받되 매매는 **deterministic 환원 + confirm**으로 안전화하고 모든 명령은
file-drop을 거쳐 **단일 워커 + 기존 RiskManager→Broker 게이트**로 실행된다. 운영자 command 권한은
advisor-only agent 세션에서 **구조적으로 접근 불가**(권한 분리, 이번 트랙의 핵심 보안 제약). agent와의
밀접한 communication은 **읽기 + 이벤트 푸시 + 경량 양방향 질의 + 부분적 지시 주입**으로 v1에 담고,
F3는 재구현된 엔진 위로 재정렬된다.

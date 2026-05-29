# 도메인 엔티티 — Unit A `steering-core` (F4)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit A · Functional Design · 2026-05-29._
_기술 비종속. 코드 식별자/경로는 영문 유지. F4 = F2의 안전 모델을 detached + file-drop로 재구현._

> **F2 대비 핵심 변화**: in-process prompt_toolkit 콘솔이 사라지고, 운영자 인터페이스가 **별도 프로세스
> (Unit B, opencode 베이스)** 가 된다. 둘은 **repo-root `steering/`** 의 append-only 파일로만 통신한다.
> `y`/`CONFIRM` 확인은 **Unit B에서** 끝나고(Q2=A), 데몬은 **이미 확정된 구조화 명령 레코드**만 받는다.

---

## 변경 없이 계승하는 엔티티 (F2 → F4 동일)
아래는 F2 functional-design `domain-entities.md`의 정의를 그대로 계승한다(저장 위치만 §끝 표 참조).
- **E1 `Decision.source`** (`Literal["agent","human"]`, 기본 `"agent"`) — 하위호환, 사람 거래 태깅 + 락 트리거 판정.
- **E2 `InterventionRecord`** — 모든 개입의 append-only 영구 로그(ts/kind/raw/command/args/outcome/detail/rationale).
  `raw`는 이제 **운영자 도구가 보낸 원문 자연어**(또는 환원된 명령)도 담는다. pydantic, 비밀정보 0(SECURITY-03/13).
- **E3 `RunState`** — `paused`/`entries_halted`. 인메모리 + **ET-date 영속**(`run_state.json`, BR-3.3).
- **E4 `HumanLock`** — 사람-락 상태머신(`locked`/`denied`, `reject_count` 0→1→2). ET-date 스코프. (상태전이는 F2 E4 그대로.)
- **E5 `PendingApproval`** — 락 종목에 대한 에이전트 재량 결정의 승인 대기 큐(id/decision/created_ts/status/reason).
- **E6 `Directive`/Note** — 상시 지시(`directives.jsonl`) / 일회성 맥락(로그).

---

## F4 신규 엔티티

### E7. `SteeringCommand` (file-drop 명령 레코드) — 신규 핵심
운영자 도구(Unit B)가 **확인을 마친 뒤** `steering/commands.jsonl`에 append하는 구조화 명령. 데몬의
file-drop 리더가 읽어 검증 후 CommandQueue에 싣는다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | `str` (UUID) | 운영자 도구가 발급. **outcome 상관 키**(Q4=A) + 멱등 처리 키. |
| `ts` | `datetime` | 발행 시각(운영자 측). |
| `verb` | `Literal["buy","sell","flatten","flatten_all","stop","pause","resume","halt_entries","allow_entries","kill","approve","reject","unlock","cancel","note","directive","directive_clear","answer"]` | 결정적 동사(자연어가 아닌 환원 결과). |
| `args` | `dict` | 검증 대상 인자: `symbol`/`size`/`unit`(`$`·`sh`·`%`)/`price`/`id`/`text`/`reason` 등. |
| `confirmed` | `bool` | 항상 `True`(Q2=A — 미확인 명령은 채널에 오지 않음). `False`면 데몬이 거부(fail-closed). |
| `token` | `str` | **운영자 인증 토큰**(BR-10). 데몬이 검증; 불일치/누락 → 거부. 로그·이벤트에 **값 미기록**(SECURITY-03). |
| `source` | `Literal["human"]` | 항상 `"human"`. |

- pydantic 모델(SECURITY-13 안전 역직렬화). **속성(PBT-02):** round-trip 동일. **(PBT-03):** 유효
  size 스펙 없는 거래 verb는 실행 가능 형태로 통과 못 함; `%`는 (0,1] frac; `confirmed=True`·`token` 유효일 때만 실행.
- **주의:** 데몬은 자연어를 파싱하지 않는다. NL→`verb`/`args` 환원은 Unit B 책임. Unit A는 **이 스키마(계약)** 와
  결정적 검증만 소유.

### E8. `SteeringEvent` (이벤트/결과 채널 레코드) — 신규
데몬이 `steering/events.jsonl`에 append하고 운영자 도구가 tail한다(FR-6).

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | `str` | 이 이벤트의 id. **outcome 이벤트는 유발 `SteeringCommand.id`를 `corr_id`로** 실어 상관(Q4=A). |
| `corr_id` | `str \| None` | 명령 결과일 때 원 명령 id. 비-명령 푸시(체결/결정/질문)면 `None`. |
| `ts` | `datetime` | 발생 시각. |
| `kind` | `Literal["outcome","fill","decision","pending","agent_question","lifecycle","reconcile"]` | 이벤트 종류. |
| `payload` | `dict` | 사람이 읽을 요약 + 구조화 필드(예 outcome: `executed`/`no_order`/`rejected`/`error` + detail). 비밀정보 0. |

- outcome 이벤트는 `InterventionRecord.outcome/detail`과 일관. 멱등: 같은 `corr_id` outcome 중복 발행 금지.

### E9. `AgentQuestion` (양방향 질의) — 신규 [FR-7, Q5=D]
에이전트가 사람에게 남기는 질문. 에이전트는 자기 영역(`workspace/`)에 쓸 수 있으므로 저장은
`workspace/agent_questions.jsonl`. 데몬이 신규 질문을 감지해 `SteeringEvent(kind="agent_question")`로 푸시.

> **⚠ /critic #7 반영 — append-only 유지(인플레이스 rewrite 금지):** `agent_questions.jsonl`은 **에이전트가 append**하므로,
> 데몬이 같은 파일의 `status`를 *덮어쓰면* writer/writer 레이스 + append-only 위반이 된다. → **status/answer는 별도
> `workspace/agent_answers.jsonl`(데몬 writer, id 키)에 기록**하고, 읽을 때 question.id로 **조인**해 open/answered 판정.
> 양쪽 다 torn-safe 공유 리더(BR-11.1)로 읽는다. 파일 **무한 성장 방지**(ET-date 스코프 또는 회전). 답변이 실제로
> 에이전트 프롬프트에 주입되는지는 **코드젠 배선 검증 항목**.

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | `str` | 질문 id. |
| `ts` | `datetime` | 등록 시각. |
| `symbol` | `str \| None` | 관련 종목(있으면). |
| `text` | `str` | 질문 본문. |
| `status` | `Literal["open","answered"]` | 처리 상태. |
| `answer` | `str = ""` | 사람 답변(있으면). |
| `answered_ts` | `datetime \| None` | 답변 시각. |

- 사람이 `verb="answer"`(`args.id`,`args.text`)로 응답 → 데몬이 해당 질문 `answered`로 갱신 + **reconcile 트리거**
  (에이전트가 다음 턴/리콘사일에서 답을 읽고 반영). v1 경량(질문 적재 + 응답 라우팅; 풍부한 협상은 추후).

### Snapshot (영속 엔티티 아님 — 게시 뷰) [C-3 반영]
데몬이 주기적으로 `steering/snapshot.json`에 게시하는 **읽기 전용 라이브 뷰**(운영자 `/status·/positions·/orders`용).
F2의 toolbar 캐시를 파일로 외부화한 것 + **C-3 보강(포지션/미체결주문/체결 커서 포함)**:
`run_state`, 락/denied/pending 요약, **positions, open_orders, 최근 fills 커서**, market_open, 갱신 ts.
운영자 도구는 이 파일을 읽어 표시(데몬 라운드트립 불필요). 에이전트 journal/trace는 운영자가 **직접 read-only**로 읽음.

---

## 저장 위치 표 (권한 경계 명시 — NFR-1)
| 엔티티/채널 | 경로 | writer | reader | 비고 |
|---|---|---|---|---|
| `SteeringCommand` | **`steering/commands.jsonl`** (repo-root, workspace 밖) | 운영자 도구(Unit B) | 데몬 | **에이전트 쓰기 금지**(BR-10) |
| `SteeringEvent` | **`steering/events.jsonl`** | 데몬 | 운영자 도구 | append-only |
| Snapshot | **`steering/snapshot.json`** | 데몬 | 운영자 도구 | 라이브 뷰 |
| 처리 커서 | **`steering/.commands_cursor`** | 데몬 | 데몬 | 재시작 멱등(BR-11) |
| `InterventionRecord` | `workspace/human_directives.jsonl` | 데몬 | 에이전트/감사 | append-only |
| `RunState` | `workspace/run_state.json` 또는 `steering/` | 데몬 | 데몬 | ET-date |
| `HumanLock` | `workspace/human_locks.json` | 데몬 | 데몬/executor | ET-date |
| `PendingApproval` | `workspace/pending_approvals.jsonl` | 데몬 | 데몬 | ET-date |
| `Directive` | `workspace/directives.jsonl` | 데몬 | 에이전트(프롬프트) | active 목록 |
| `AgentQuestion` | `workspace/agent_questions.jsonl` | **에이전트** | 데몬 | FR-7 |

> 핵심: **명령 채널(`steering/commands.jsonl`)만이 "쓰면 거래가 일어나는" 권한 경로**다. 이 파일은
> workspace 밖 + 토큰 검증(BR-10)으로 **에이전트가 구조적으로 쓸 수 없게** 한다. 나머지 `workspace/`
> 파일은 에이전트가 읽거나(지시/질문) 쓰더라도(질문) 주문 권한과 무관.

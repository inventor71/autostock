# Unit 1 `agent-eval-persistence` — Functional Design

> Track F41 · Construction · 2026-06-03 · 요구사항 FR-1, FR-2, FR-5 / NFR-1,2,4,5

## 1. 목표
research turn이 multi-agent로 돌 때 **각 agent/라운드의 평가를 영속**하고(FR-1),
multi-agent `record_turn`의 **빈 `turn_id`/`summary` 버그를 수정**한다(FR-2).
추가 LLM 호출 없음(NFR-2), turn 흐름 무영향 best-effort(NFR-1).

## 2. 통일 평가 스키마

신규 모듈 `src/agent/agent_reports.py`. turn당 JSON 1개를 사이드카로 저장.

```text
AgentEval:
  index:   int                 # 0-based 표시 순서
  label:   str                 # 예 "Round 1 · Initial", "Agent 2 · Discovery"
  role:    str                 # 짧은 역할/태스크 요약 (한 줄)
  status:  "ok" | "error" | "timeout"
  text:    str                 # 그 agent/라운드 평가 전문 (절단 금지)
  error:   str | None          # status != ok 일 때 사유

AgentReport (turn당 1 레코드):
  turn_id:    str              # "" 면 ts로 키
  et_date:    str              # compute_et_date(ts)
  ts:         str              # tz-aware ISO (turn 종료 시각)
  turn_type:  "research"
  mode:       "sequential" | "parallel"
  n_agents:   int
  agents:     [AgentEval, ...] # 표시 순서대로
  synthesis:  { text: str }    # 최종 합성/최종 라운드 텍스트
```

### 모드별 채움 매핑
| 모드 | `agents[]` | `synthesis.text` |
|------|-----------|------------------|
| sequential | R1 initial, R2..R(n-1) debate, 각 `run_turn().result` (라벨 "Round k · Initial/Debate") | 마지막 synthesis 라운드 `result.result` |
| parallel | 각 `SubAgentReport` → AgentEval(label "Agent i · \<task 첫 문장\>", role=task.description 요약, status=completed?ok:error, text=result_text, error) | 합성 세션 `result.result` |

- sequential 라운드 라벨: 1=Initial, 1<k<n=Debate k, 마지막=Synthesis(이는 synthesis 필드와 중복되므로
  `agents[]`에는 Initial+Debate만 넣고 synthesis는 별도 필드로 — 표시 일관성). **결정:** `agents[]`에는
  비-synthesis 라운드만, 최종 라운드는 `synthesis.text`. (parallel도 sub-agents만 `agents[]`, 합성은 synthesis.)

## 3. 저장 위치 / 조회
- 디렉터리: `journal.root / "agent_reports"` (예 `workspace/agent_reports/`).
- 파일명: `<turn_id>.json` (turn_id 비면 `<ts-safe>.json`, ts의 `:`→`-`).
- API:
  - `write_agent_report(root: Path, report: dict) -> Path` — `mkdir parents`, atomic write(tmp+rename).
  - `read_agent_report(root: Path, turn_id: str) -> dict | None`.
  - `has_agent_report(root, turn_id) -> bool` (모니터가 목록 표시 여부 판단).
- 보존: turn당 1파일. 정리 정책은 범위 밖(turns.jsonl과 동일 라이프사이클 가정).

## 4. orchestrator 변경 (FR-1 + FR-2)

`_run`의 텔레메트리 동작을 multi-agent 두 경로에도 정합시킨다:

공통(두 경로):
1. 시작 시 `turn_id = generate_turn_id(turns_path, "research")`, `started_at` 기록,
   `self.last_turn_id = turn_id`, `_on_turn_start(turn_id, "research")` 호출(가능하면).
2. 종료 시 `last_new_decisions`에 `d.turn_id = turn_id` 태깅(현재 단일경로만 함 → 결정-턴 상관 정확도↑).
3. `record_turn(..., turn_id=turn_id, summary=build_turn_summary("research", last_new_decisions, llm_text=<synthesis result.result>), started_at=started_at, error=...)`.
4. `_on_turn_end()` 호출(가능하면).
5. agent 평가 수집 → `write_agent_report(...)` **best-effort**(try/except 로깅, turn 실패시키지 않음, NFR-1).

sequential 전용:
- 각 `run_turn` 결과를 리스트로 모은다(initial, debate들, synthesis). `agents[]`=비-synthesis,
  `synthesis.text`=마지막. 예외 시 reset 후 raise는 유지하되, 이미 모은 부분 평가는 best-effort 영속(선택; 최소구현은 성공 경로만).

parallel 전용:
- 이미 있는 `reports: list[SubAgentReport]`를 AgentEval로 변환(완료/실패/타임아웃 status 반영).
- 합성 세션 `result.result` → synthesis.text.
- fallback(단일 세션) 경로로 빠지면 `_run`이 모든 텔레메트리를 처리하므로 agent_report 미작성(목록도 안 뜸) — 정상.

> FR-5 무회귀: 단일 세션 `_run` 경로는 변경 없음(이미 turn_id/summary 채움). 비-research turn 무관.

## 5. 마스킹 (NFR-4)
영속 텍스트는 로컬 workspace(이미 decisions/reasons 평문 저장) → **쓰기 시 마스킹 안 함**.
비밀값 노출 방지는 **표시 경로(Unit 2)** 에서 기존 `runtime._mask_secrets` 재사용으로 처리.
(FD에 명시: Unit 2가 노출 시 마스킹.)

## 6. 테스트 (NFR-5)
- `agent_reports` write→read 라운드트립(turn_id 키 / ts 키 fallback), atomic write.
- sequential 캡처: n_agents=3 → agents 2개(Initial,Debate1)+synthesis, 라벨 정확.
- parallel 캡처: 완료/실패 혼합 → status 매핑, 합성 텍스트.
- record_turn FR-2: 두 경로가 turn_id 비어있지 않게, summary 비어있지 않게 기록(가짜 session runner로).
- best-effort: write_agent_report가 raise해도 turn 결과 반환됨.
- 회귀: 기존 orchestrator/turn_log 테스트 green.

## 7. 영향 파일
- 신규: `src/agent/agent_reports.py`, `tests/.../test_agent_reports.py`(+ orchestrator 캡처 테스트).
- 수정: `src/agent/orchestrator.py` (`_run_sequential_research`, `_run_parallel_research`).
- 재사용: `src/agent/turn_log.py` (`build_turn_summary`, `generate_turn_id`, `compute_et_date`).

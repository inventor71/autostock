# F41 — Research turn 마커 오버레이 정보 강화 (요구사항)

> Track F41 · Brownfield · Standard depth · 2026-06-03
> 단일 작성자 = F41 worktree 세션. 승인 게이트 통과 전 다음 단계로 넘어가지 않음.

## 1. 배경 / 문제

타임라인에서 research turn 마커를 클릭하면 뜨는 오버레이
(`operator-console/cli/packages/tui-trading/src/components/turn-overlay.tsx`)가
충분히 informative하지 않다. 스크린샷의 06-02 turn은 헤더 한 줄만 뜬다:

```
[] research · 2026-06-02T21:42:52+09:00 · 177s · $1.83 · 3 dec
```

코드 역추적으로 확인한 근본 원인 2개:

1. **빈 summary (버그).** 06-02 turn은 multi-agent(sequential) turn이다.
   `orchestrator._run_sequential_research` / `_run_parallel_research`의
   `record_turn(...)` 호출은 단일 세션 경로(`_run`)와 달리 `build_turn_summary(...)`를
   호출하지 않아 `summary=""`로 기록된다. 또 `turn_id`도 비어 헤더의 `[]`가 빈다.
   → 오버레이가 표시할 본문이 없다.
2. **agent별 평가가 영속되지 않는다.** parallel 모드의 `SubAgentReport.result_text`는
   synthesis 프롬프트에 합쳐진 뒤 임시 워크스페이스와 함께 삭제된다. sequential 모드는
   한 세션의 R1(initial)→R2(debate)→R3(synthesis) 라운드라 라운드별 결과 텍스트가 어디에도
   남지 않고, 서술은 `workspace/daily/<date>.md` 내러티브에만 존재한다.

운영 설정: `config/settings.yaml` → `multi_agent: {enabled: true, mode: sequential, n_agents: 3}`.
parallel은 옵션(mode C). **두 모드 모두 지원해야 한다.**

## 2. 사용자 결정 (clarifying questions, 2026-06-03)

| # | 질문 | 결정 |
|---|------|------|
| Q1 | 정보 깊이/소스 | **agent별 평가 전체 + 종합근거** (각 agent/라운드 평가를 영속·노출 + synthesis가 어떻게 합쳐졌는지) |
| Q2 | 오버레이 UX | **drill-down 패널** (오버레이엔 agent 목록만; 한 항목 클릭 → 큰 패널/전체에서 그 평가 전문) |
| Q3 | 적용 범위 | **research turn만** |
| Q4 | extension 룰 | Security Baseline·PBT **둘 다 스킵** (내부 운영자 TUI/저널 개선) |

## 3. 용어 정리 — "agent" 매핑

| 실행 모드 | drill-down 목록의 한 항목 | 영속 대상 |
|-----------|---------------------------|-----------|
| sequential (운영 기본) | **Round 1 Initial / Round k Debate / Round n Synthesis** | 각 `session.run_turn(...)`의 `result.result` 텍스트 + 라운드 라벨 |
| parallel (옵션) | **Agent i · \<task 요약\>** (+ Synthesis) | 각 `SubAgentReport` (task.description, result_text, completed, error) + 최종 synthesis 텍스트 |

두 모드의 영속 산출물은 **동일한 스키마**로 통일한다(아래 FR-1). drill-down UI는 모드와 무관하게
"항목 목록 → 항목 전문" 패턴 하나로 동작한다.

## 4. 기능 요구사항 (FR)

### FR-1 — multi-agent 평가 영속 (Python)
research turn이 multi-agent로 실행되면, 각 agent/라운드의 평가를 turn 단위로 영속한다.
- **스키마(제안, 설계에서 확정):** turn당 한 레코드. 필드:
  `turn_id`, `et_date`, `ts`, `mode`("sequential"|"parallel"), `n_agents`,
  `agents: [{ index, label, role, status("ok"|"error"|"timeout"), text, error? }]`,
  `synthesis: { text }`.
  - sequential: `agents`는 라운드들(initial/debate/synthesis 라운드), `synthesis.text`는 최종 라운드 텍스트.
  - parallel: `agents`는 sub-agent 리포트들, `synthesis.text`는 합성 세션 텍스트.
- **저장 위치(제안):** `turns.jsonl` 비대화 방지를 위해 **사이드카** —
  예 `workspace/agent_reports/<turn_id>.json` (turn_id로 조회). turn_id가 비면 ts로 키.
- **`text`는 절단하지 않는다**(전문 보존). 표시 측에서 길이 제어.

### FR-2 — multi-agent turn summary/turn_id 버그 수정 (Python)
`_run_sequential_research` / `_run_parallel_research`의 `record_turn(...)`이 단일 세션 경로처럼
`turn_id`(generate_turn_id)와 `summary`(build_turn_summary, 결정 + 분석 스니펫)를 채운다.
→ 오버레이 헤더가 `[R5] …`로, summary 줄이 채워진다. (과거 빈 레코드는 소급 수정하지 않음.)

### FR-3 — 평가 데이터 노출 (steering/monitor → TUI)
TUI가 turn별 agent 평가를 읽을 수 있어야 한다. 라이브 모니터 경로와 **과거 세션** 경로
(F36에서 추가된 historical 읽기) 모두에서 동작:
- 라이브: `publish_monitor` / `steer_read` 응답이 turn에 agent 평가 존재 여부 + 데이터를 제공.
- 과거: TUI가 날짜별 세션 데이터를 읽을 때 사이드카도 함께 조회.
- 정확한 전송 형태(인라인 vs on-demand fetch)는 설계에서 확정(오버레이 payload가 커질 수 있어
  on-demand 가능성 고려).

### FR-4 — drill-down 오버레이 (TUI)
`turn-overlay.tsx`가 research multi-agent turn에 대해:
- 헤더 + synthesis 한 줄 요약 + 기존 결정 리스트(현행 유지) **아래에** "Agents (click to open)" 목록 표시.
  각 항목: 라벨(Round/Agent) + role 요약 + status 마크(✓ / ✗ / ⏱).
- 항목 클릭 → 큰 패널/전체 영역에서 그 agent/라운드 평가 **전문**을 스크롤로 표시
  (좁은 기본 오버레이로는 전문이 안 들어가므로). 뒤로가기로 목록 복귀.
- multi-agent가 아닌 turn / 데이터 없음: 현행 표시 그대로(목록 미표시), 회귀 없음.

### FR-5 — 비대상 turn 무회귀
intraday/wake/eod 등 비-research, 그리고 단일 세션 research turn은 동작이 바뀌지 않는다
(FR-2의 summary 채움은 multi-agent 경로에 한정; 단일 경로는 이미 채움).

## 5. 비기능 요구사항 (NFR)
- **NFR-1 영향 격리:** 영속/수집은 turn 실행 스레드에서 best-effort, 실패해도 turn/거래 흐름을
  막지 않는다(로깅만). 기존 turn 텔레메트리와 동일한 결함 허용.
- **NFR-2 비용:** 추가 LLM 호출 없음 — 이미 생성된 라운드/리포트 텍스트를 **캡처만** 한다.
- **NFR-3 페이로드:** agent 전문은 길 수 있다. 오버레이 기본 payload를 부풀리지 않도록
  목록은 가볍게, 전문은 drill-down 시 로드(설계에서 확정).
- **NFR-4 데이터 위생:** 표시 텍스트에 비밀값이 새지 않게 기존 `_mask_secrets` 정책과 정합.
- **NFR-5 테스트:** Python 영속/요약/스키마 라운드트립 단위 테스트, TUI 데이터 매핑 테스트.

## 6. 영향 코드 (예비)
- Python: `src/agent/orchestrator.py`(영속 캡처 + record_turn 수정),
  `src/agent/turn_log.py`(summary 재사용), 신규 영속 모듈/스키마,
  `src/agent/steering/runtime.py`(`_turns_summary`/`publish_monitor` 노출).
- TUI: `operator-console/cli/packages/tui-trading/src/` — `types.ts`,
  `components/turn-overlay.tsx`(drill-down), 데이터 hook(`use-session-data.ts` 등),
  과거 세션 읽기 경로.

## 7. 범위 밖 (Out of scope)
- 과거 빈 summary/turn_id 레코드 소급 보정.
- intraday/wake/eod의 agent별 분해(multi-agent는 research에만 존재).
- 새 LLM 분석/요약 생성(추가 비용). 캡처/표시만.
- parallel 모드를 운영 기본으로 전환(설정은 사용자 소관).

## 8. 가정
- sequential 모드에서 각 `run_turn` 결과 텍스트가 그 라운드의 평가를 대표한다.
- F36의 historical 세션 읽기 경로가 사이드카 조회의 자연스러운 확장점이다.

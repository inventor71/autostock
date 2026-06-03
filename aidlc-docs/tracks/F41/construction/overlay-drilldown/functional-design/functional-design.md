# Unit 2 `overlay-drilldown` — Functional Design (lite)

> Track F41 · Construction · 2026-06-03 · 요구사항 FR-3, FR-4, FR-5 / NFR-3,4,5

## 1. 핵심 통찰 — 노출 경로
TUI는 이미 `monitor.workspace_root`로 저널 파일(`turns.jsonl`/`decisions.jsonl`/
`human_directives.jsonl`)을 **직접** 읽는다(`use-session-data.ts`, F36 historical 경로).
agent 평가 사이드카(`agent_reports/<turn_id>.json`)도 **같은 방식으로 직접 읽으면**
라이브/과거 세션 모두에서 동작하고 `monitor.json`을 부풀리지 않는다(NFR-3 on-demand).
→ `steering/runtime.py` 변경 불필요. 순수 TS 작업.

## 2. 데이터 (TS)
- `types.ts`: `AgentEval { index, label, role, status, text, error? }`,
  `AgentReport { turn_id, et_date, ts, turn_type, mode, n_agents, agents[], synthesis{text} }`.
- `use-session-data.ts`: `readAgentReport(root, turnId): AgentReport | null` —
  `agent_reports/<turnId>.json` 읽기, 부재/파싱오류 시 null. 표시 텍스트에 `maskSecrets()`
  적용(NFR-4; Python `_mask_secrets`와 동치: secret kv + 장문 opaque blob).

## 3. 오버레이 (FR-4, drill-down)
`turn-overlay.tsx`에 `workspaceRoot` prop 추가. App(session route)이 `workspaceRoot()` 전달.
- 마운트 시 turn_id로 `readAgentReport` 시도(memo). 보고서 있으면:
  - **목록 뷰(기본)**: 기존 헤더+요약+결정 리스트 **아래에** `Agents (click to open):` 목록.
    각 항목 = 라벨 + status 마크(✓ ok / ✗ error / ⏱ timeout). 클릭 → 그 항목 drill-down.
  - **drill-down 뷰**: 선택 항목의 라벨/role + 전문(`text`)을 `<scrollbox>`로 표시.
    `‹ back` 클릭 → 목록 복귀. drill-down일 땐 패널을 넓게/높게(예 width≈100, height≈30)
    렌더(좁은 기본 오버레이로는 전문이 안 들어감).
  - synthesis 텍스트는 목록 뷰의 마지막 항목 또는 헤더 요약으로도 접근 가능.
- 보고서 없음(단일세션/비-multi-agent/구 레코드): 기존 표시 그대로(목록 미표시) — 무회귀(FR-5).
- 상태: `createSignal<number | null>(openAgent)`. 오버레이 닫힘/turn 변경 시 리셋.

## 4. 테스트 (NFR-5)
- `readAgentReport`: 정상 읽기/부재 null/손상 null/마스킹.
- (가능하면) 오버레이 목록↔drill-down 렌더 스냅샷은 비용 대비 낮음 → `readAgentReport`
  단위 + 타입 컴파일(`bun run typecheck`)로 커버.

## 5. 영향 파일
- 수정: `packages/tui-trading/src/types.ts`,
  `packages/tui-trading/src/hooks/use-session-data.ts`,
  `packages/tui-trading/src/components/turn-overlay.tsx`,
  `packages/opencode/src/cli/cmd/tui/routes/session/index.tsx`(prop 전달).
- 신규 테스트: `packages/tui-trading/test/agent-report.test.ts`.

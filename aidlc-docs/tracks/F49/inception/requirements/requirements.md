# F49 Requirements — synthesis final verdict TUI display bug fix

## Intent Analysis

- **User Request**: "[Image #1] synthesis final verdict가 이렇게 깨져서 나올때가 있는데 버그인듯 수정"
- **Request Type**: Bug Fix
- **Scope Estimate**: Single Component (`turn-overlay.tsx`)
- **Complexity**: Simple (1-line JSX attribute fix)

## User Answers Summary

| Question | Answer | Interpretation |
|----------|--------|----------------|
| Q1: 증상 | X (스크린샷 참조) + "텍스트가 일부 겹쳐보임" | Text lines overlap visually |
| Q2: 발생 조건 | E (간헐적) | Intermittent, depends on synthesis text content |
| Q3: 깨지는 위치 | B (텍스트 라인들만) | Text rendering issue, not layout/scroll |
| Q4: 발생 턴 | 06-03 21:30경 research, $0.93, 1dec | R4 turn specifically |
| Q5: Security | B (적용 안 함) | Disabled for this track |
| Q6: PBT | C (적용 안 함) | Disabled for this track |

## Root Cause Analysis

### Problem
Turn overlay에서 "Synthesis · final verdict" drill-down 시 텍스트 라인이 겹쳐 보이는(garbled/overlapping) 렌더링 버그.

### Affected Code
`operator-console/cli/packages/tui-trading/src/components/turn-overlay.tsx:157-158`:
```tsx
<For each={(e.text || "(no text)").split("\n")}>
  {(line) => <text fg="white">{line}</text>}
</For>
```

### Root Cause
`<text>` 엘리먼트에 `wrapMode`가 명시되지 않음. opentui `@opentui/core`의 `TextBufferRenderable` 기본 `wrapMode`는 `"none"`임.

Synthesis 텍스트는 LLM 출력으로, 마크다운 테이블 등 400~500자 길이의 라인을 포함함. Overlay 너비는 최대 ~98컬럼(`Math.min(100, termWidth - 2) - padding`)임. `wrapMode="none"` + 500자 라인 → Yoga 레이아웃에서 텍스트 엘리먼트의 측정 너비가 500컬럼이 되고, scrollbox 컨텐츠 영역이 뷰포트를 크게 초과함. 이로 인해 렌더링 시 텍스트 라인이 겹쳐 보이는(overflow→overlap) 현상 발생.

opencode 프로젝트의 다른 모든 텍스트 컴포넌트(`scrollback.writer.tsx` 등)는 `wrapMode="word"`를 명시적으로 사용하여 이를 방지함.

### Fix
`turn-overlay.tsx:158`의 `<text>` 엘리먼트에 `wrapMode="word"` 추가:

```tsx
<For each={(e.text || "(no text)").split("\n")}>
  {(line) => <text fg="white" wrapMode="word">{line}</text>}
</For>
```

`wrapMode="word"`는 단어 경계에서 텍스트를 래핑하여 scrollbox 너비 내에서 표시함. markdown 테이블은 단어 단위로 래핑되어 가독성이 유지됨.

### Why intermittent?
- synthesis 텍스트 내용에 따라 라인 길이가 달라짐
- 짧은 라인만 있는 경우(대부분 100자 미만)는 문제가 발생하지 않음
- 긴 라인(400자 이상)이 포함된 턴에서만 overflow 발생

## Functional Requirements
- **FR-1**: synthesis final verdict drill-down 시 텍스트가 overlay 너비 내에서 word-wrap되어 표시되어야 함
- **FR-2**: wrapMode 변경이 다른 entry(agent evaluations)의 drill-down에도 적용되어야 함 (동일한 코드 경로)

## Non-Functional Requirements
- **NFR-1**: wrapMode 변경이 TUI 렌더링 성능에 부정적 영향을 주지 않아야 함
- **NFR-2**: 기존 44개 tui-trading 테스트가 모두 통과해야 함

## Extension Configuration
- **Security Baseline**: Disabled (순수 UI 표시 버그 수정, 보안 관련 코드 변경 없음)
- **Property-Based Testing**: Disabled (UI 렌더링 속성 변경, PBT 대상 로직 없음)

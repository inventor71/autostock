# F57 — Build & Test Summary

단일 단위(NavRow) 버그 수정. 변경 파일 1개:
`operator-console/cli/packages/tui-trading/src/components/timeline-bar.tsx` (`NavRow` 함수).

## 변경 내용
1. status 칩 내부 `<box>` 에 `flexDirection="row"` 추가 → `"● "` 와 라벨 동일선 유지
   (기존 기본 `column` 으로 세로 적층 → NavRow 2줄 → `height={3}` 초과 → 바 깨짐).
2. `void props.blinkOn` 을 `<Show>` 자식 본문에서 반응형 `label()` 계산 내부로 이동
   → 500ms blink 틱마다 `fmtTurnLabel(..., Date.now())` 재계산 → 경과시간 실시간 증가.

## Build
- 별도 빌드 산출물 없음(소스 TS/TSX, bun 런타임이 직접 실행). 빌드는 소비 패키지
  `packages/opencode` 의 번들 경로에 포함됨.

## Unit Test — PASS
```
cd operator-console/cli/packages/tui-trading
bun test test/progress-label.test.ts
→ 8 pass / 0 fail (fmtElapsedClock, fmtTurnLabel 포맷 검증)
```
타이머 값 계산(`fmtTurnLabel`)은 회귀 없음을 단위테스트로 확인. 이번 버그는 값 계산이
아니라 **반응형 재계산 트리거 누락**이었으므로, 재계산 트리거(blink 추적)는 TickRow/
MarkerRow now-cursor blink 와 동일한 검증된 패턴으로 동작.

## Typecheck — PASS (changed file)
```
bunx tsgo --noEmit -p packages/tui-trading/tsconfig.json   (main node_modules 임시 심볼릭)
→ timeline-bar.tsx: 오류 0건.
   (hooks/*.ts 의 fs/path "Cannot find module" 은 standalone tsconfig `types:[]` 로 인한
    선재(pre-existing) 격리 아티팩트 — opencode 소비 시 node/bun 타입 제공. 본 변경 무관.)
```

## Integration / Live Smoke
- 순수 TUI 렌더 변경. 통합 테스트 대상 외부 시스템 없음.
- 라이브 육안 확인 권장 항목(머지 후 또는 docker-verify attach):
  - [ ] 상단 바가 **한 줄**로 유지(status + 날짜 nav 동일선).
  - [ ] in-flight research turn 시 `research · Xs` 경과시간이 **초 단위로 증가**.

## 결과: 전 항목 GREEN → 트랙 `merge-awaiting`.

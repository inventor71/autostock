# Code Generation Plan — Unit B: tui-components (TypeScript)

## 유닛 컨텍스트
opencode 포크(Solid.js + OpenTUI)에 `packages/tui-trading/` 패키지를 생성하고,
타임라인 바 + 턴/심볼 오버레이를 구현한다. 0 new runtime deps.

## 서브모듈 게이트
Part 2 첫 액션으로 서브모듈(`operator-console/cli`) 내에 `feat/F22` 브랜치 생성.
부모 gitlink는 머지 시에만 커밋.

---

## Step 0: 서브모듈 브랜치 생성
- [x] `git -C .claude/worktrees/F22/operator-console/cli switch -c feat/F22`
- [x] 레지스트리 행 서브모듈 브랜치 업데이트

## Step 1: 패키지 스캐폴딩
- [x] `packages/tui-trading/package.json` 생성 (name, deps: @opentui/solid, solid-js 등 catalog:)
- [x] `packages/tui-trading/tsconfig.json` 생성 (extends opencode tsconfig)
- [x] `packages/tui-trading/src/index.ts` — 패키지 진입점 (빈 export)
- [x] `packages/tui-trading/src/types.ts` — MonitorData, MonitorTurn, MonitorDecision 등 타입 정의
- [x] opencode `package.json`에 `"@tui-trading": "workspace:*"` 추가
- [x] bun install 확인

## Step 2: 데이터 훅
- [x] `src/hooks/use-monitor-data.ts` — monitor.json 폴링 (1.5s), createSignal 반환
- [x] `src/hooks/use-snapshot-data.ts` — snapshot.json 읽기 (심볼 포지션 조회용)
- [x] `src/hooks/use-thesis.ts` — positions/SYMBOL.md 파일 읽기 (SECURITY-03: 경로 검증)
- [x] `src/hooks/use-overlay.ts` — 오버레이 상태 관리 (open/close/toggle)

## Step 3: 유틸리티
- [x] `src/utils/timeline-layout.ts` — 시간축 계산 (HH:MM → x좌표 매핑, 범위 결정)
- [x] `src/utils/format.ts` — 포맷팅 (시간, 가격, P&L 색상, 마커 glyph/color 매핑)

## Step 4: TimelineBar 컴포넌트
- [x] `src/components/timeline-bar.tsx` — 2줄 타임라인 바
  - 시간 눈금 행 (줄1)
  - 마커 행 (줄2): 각 턴의 glyph를 시간 위치에 배치
  - 진행 중 마커 (◎, 깜빡임)
  - 현재 시점 표시 (→ now)
  - 마커 클릭 → onMarkerClick(turnId, x, y)
  - 빈 상태: "No turns today" / "Monitor disconnected"

## Step 5: 오버레이 컴포넌트
- [x] `src/components/overlay-panel.tsx` — 공통 플로팅 패널 래퍼
  - position="absolute", zIndex=2000
  - 화면 경계 보정
  - 배경/테두리 (theme 활용)
  - 패널 밖 클릭 → onClose
- [x] `src/components/turn-overlay.tsx` — 턴 상세 오버레이
  - 턴 메타: [ID] Type · HH:MM · dur · $cost · N dec
  - 요약: summary 텍스트
  - 결정 목록: 색상 코딩 (BUY=green, SELL=red, HOLD=muted, ADJUST=yellow)
  - 심볼 텍스트 클릭 → 심볼 오버레이 전환
- [x] `src/components/symbol-overlay.tsx` — 심볼 논거 오버레이
  - 심볼 헤더: SYMBOL · 현재가
  - 포지션 정보 (있으면): qty, entry, P&L
  - Thesis 내용: md 파일 텍스트 (최대 10줄)
  - 최근 결정: 마지막 3개

## Step 6: Session 레이아웃 통합
- [x] `packages/opencode/.../routes/session/index.tsx` 수정:
  - `session_top` 슬롯 추가 (또는 직접 TimelineBar import)
  - TimelineBar에 터미널 너비 전달
- [x] `packages/tui-trading/src/index.ts`에서 TimelineBar + OverlayContainer export
- [x] OverlayContainer를 Session 레이아웃에 배치 (절대 위치)

## Step 7: 빌드 + 기능 확인
- [x] bun install + typecheck 통과
- [x] 로컬 실행하여 타임라인 바 렌더링 확인 (monitor.json 없을 때 "Monitor disconnected")
- [x] mock monitor.json으로 마커 표시 확인
- [x] 마커 클릭 → 턴 오버레이 표시 확인
- [x] 심볼 클릭 → 심볼 오버레이 전환 확인
- [x] ESC/밖 클릭으로 오버레이 닫기 확인

## Step 8: Python 회귀 + 통합
- [x] Python 전체 테스트 스위트 통과 (Unit A 변경 포함)
- [x] TS typecheck 통과

## Security Baseline 준수
- **SECURITY-03**: thesis 파일 경로 `workspace/positions/` 하위만 허용 (path traversal 방지)
- **SECURITY-10**: 0 new npm deps — catalog: 참조만
- **SECURITY-11**: 데이터 훅은 읽기 전용 (파일 쓰기 없음)
- **SECURITY-15**: 파일 읽기 실패 시 graceful fallback (빈 데이터)

## 예상 변경량
- 신규: `packages/tui-trading/` 전체 (~10 파일)
- 수정: `packages/opencode/.../routes/session/index.tsx` (슬롯 추가, ~5줄)
- 수정: `packages/opencode/package.json` (의존성 1줄)
- 0 new runtime deps

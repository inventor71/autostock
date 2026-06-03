# Frontend Components — Unit B: tui-components (TypeScript)

## 컴포넌트 계층 구조

```
Session (기존, 수정)
├── <Slot name="session_top" />     ← NEW
│   └── TimelineBar                 ← tui-trading 패키지
│       ├── TimelineAxis (시간 눈금)
│       ├── TimelineMarkerRow (마커 행)
│       │   ├── Marker × N (각 턴)
│       │   └── InProgressMarker (진행 중 턴, 조건부)
│       └── NowIndicator (현재 시점)
├── <box flexDirection="row">       (기존)
│   ├── Sidebar (기존)
│   └── scrollbox (기존)
├── OverlayContainer                ← tui-trading 패키지 (절대 위치)
│   ├── TurnOverlay (조건부)
│   │   ├── TurnHeader
│   │   ├── TurnSummary
│   │   └── DecisionList
│   │       └── DecisionItem × N
│   │           └── SymbolLink (클릭 가능)
│   └── SymbolOverlay (조건부)
│       ├── SymbolHeader
│       ├── PositionInfo (조건부)
│       ├── ThesisContent
│       └── RecentDecisions
└── Prompt (기존)
```

## C1: TimelineBar

### Props
```ts
interface TimelineBarProps {
  width: number    // 터미널 전체 너비
}
```

### 렌더링 (2줄)
```
줄1 (시간 눈금):  09:30     10:00     10:30     11:00     → 12:31
줄2 (마커):       ──●───────◆─────────○─────────○────◎───→
```

### 상태
- `monitor`: useMonitorData() 반환
- `selectedTurnId`: createSignal<string | null>(null)
- `blinkOn`: createSignal(true) — 0.5s 토글 (진행 중 마커용)

### 이벤트
- 마커 `onMouseUp` → overlay.openTurn(turnId, x, y)

## C2: TurnOverlay

### Props
```ts
interface TurnOverlayProps {
  turnId: string
  anchor: { x: number; y: number }
  monitor: MonitorData
  onClose: () => void
  onSymbolClick: (symbol: string, x: number, y: number) => void
}
```

### 렌더링
```
┌──────────────────────────────────┐
│ [I3] Intraday · 10:30 · 5s · $0.30  │
│ Intraday: HOLD AAPL(0.7)            │
│──────────────────────────────────│
│ ○ HOLD AAPL (0.7) Neutral outlook   │
└──────────────────────────────────┘
```

### 상태
- 턴 정보: monitor.turns.recent에서 id로 필터
- 결정 목록: monitor.decisions에서 turn_id로 필터

## C3: SymbolOverlay

### Props
```ts
interface SymbolOverlayProps {
  symbol: string
  anchor: { x: number; y: number }
  monitor: MonitorData
  snapshot: SnapshotData | null
  onClose: () => void
}
```

### 렌더링
```
┌──────────────────────────────────┐
│ AAPL · $185.30                       │
│ Qty: 10 · Entry: $180.50 · +$48.00  │
│──────────────────────────────────│
│ ## Thesis                            │
│ Strong momentum play on...           │
│ ...                                  │
│──────────────────────────────────│
│ Recent: BUY(R1) HOLD(I2) HOLD(I3)   │
└──────────────────────────────────┘
```

### 상태
- thesis: useThesis(symbol) — 파일 읽기
- position: snapshot.positions[symbol]
- decisions: monitor.decisions.filter(d => d.symbol === symbol)

## C4: OverlayPanel (공통 래퍼)

### Props
```ts
interface OverlayPanelProps {
  anchor: { x: number; y: number }
  width?: number       // 기본 50
  maxHeight?: number   // 기본 15
  onClose: () => void
  children: JSX.Element
}
```

### 동작
- `position="absolute"`, `zIndex=2000`
- 화면 경계 보정 (오른쪽/아래 넘침 시 반대쪽으로)
- 배경: `theme.backgroundPanel`, 테두리: `theme.border`
- 패널 밖 클릭 → `onClose()` (이벤트 버블링 기반)

## C5: OverlayContainer

### 위치
Session 레이아웃 최상위에 절대 위치로 배치.

```tsx
<box width={termWidth} height={termHeight} position="relative">
  {/* 기존 레이아웃 */}
  <OverlayContainer />  {/* position="absolute", 전체 화면 커버 */}
</box>
```

### 동작
- `overlayState` 시그널 구독
- `type === "turn"` → TurnOverlay 렌더
- `type === "symbol"` → SymbolOverlay 렌더
- `type === null` → 아무것도 렌더하지 않음

## 상호작용 흐름

### 턴 오버레이 열기
```
사용자 클릭 마커 (TimelineBar)
  → overlay.openTurn(turnId, x, y)
    → OverlayState = { type: "turn", turnId, anchorX: x, anchorY: y }
      → OverlayContainer가 TurnOverlay 렌더
```

### 심볼 오버레이 전환
```
사용자 클릭 심볼 (TurnOverlay 내 DecisionItem)
  → props.onSymbolClick(symbol, x, y)
    → overlay.openSymbol(symbol, x, y)
      → OverlayState = { type: "symbol", symbol, ... }
        → OverlayContainer가 SymbolOverlay 렌더
```

### 오버레이 닫기
```
사용자 패널 밖 클릭 또는 ESC
  → overlay.close()
    → OverlayState = { type: null }
      → OverlayContainer 아무것도 렌더하지 않음
```

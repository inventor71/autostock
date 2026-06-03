# Domain Entities — Unit B: tui-components (TypeScript)

## E1: MonitorData (monitor.json 파싱 결과)

TUI가 10초마다 폴링하는 `steering/monitor.json`의 파싱된 형태.

```ts
interface MonitorData {
  ts: string
  current_turn: CurrentTurn | null
  turns: TurnsBlock
  decisions: MonitorDecision[]
  log: string[]
}

interface CurrentTurn {
  id: string       // "I3"
  type: string     // "intraday"
  started_at: string // "10:31"
}

interface TurnsBlock {
  today_count: number
  today_cost_usd: number
  recent: MonitorTurn[]
}

interface MonitorTurn {
  id: string          // "R1", "I3", "W1"
  type: string        // "research", "intraday", "wake", "eod", "reconcile"
  ts: string          // "09:30" (HH:MM)
  cost_usd: number
  num_decisions: number
  duration_ms: number | null
  summary: string     // "Research: BUY AAPL(0.8), HOLD MSFT(0.5)"
  health: "ok" | "error"
}

interface MonitorDecision {
  turn_id: string | null
  ts: string          // "09:31" (HH:MM)
  symbol: string
  action: "BUY" | "SELL" | "HOLD" | "ADJUST_STOP"
  confidence: number | null
  reason: string      // 60자 truncated
  source: "agent" | "human"
}
```

## E2: SnapshotData (snapshot.json에서 심볼 오버레이용 부분)

기존 사이드바 플러그인이 이미 파싱하는 snapshot.json에서 심볼 오버레이에 필요한 부분.

```ts
interface PositionInfo {
  qty: number
  avg_entry_price: number
  current_price: number
  market_value: number
  unrealized_pnl: number
}
```

## E3: ThesisContent (positions/SYMBOL.md 파일 내용)

```ts
interface ThesisContent {
  symbol: string
  markdown: string      // 파일 전체 내용
  exists: boolean       // 파일 존재 여부
}
```

- 직접 파일 읽기 (Q4=A): `fs.readFileSync(workspace/positions/${symbol}.md)`
- 파일 없으면 `exists: false`, `markdown: ""`

## E4: TimelineMarker (타임라인 바의 각 마커)

```ts
interface TimelineMarker {
  turn: MonitorTurn           // E1의 MonitorTurn
  decisions: MonitorDecision[] // 해당 턴의 결정들 (turn_id로 필터)
  x: number                   // 타임라인 바 내 가로 위치 (col)
  glyph: string               // 마커 문자 (●, ○, ◆, ▲, ↻)
  color: string                // 마커 색상
}
```

## E5: OverlayState (오버레이 상태)

```ts
interface OverlayState {
  type: "turn" | "symbol" | null
  // turn overlay
  turnId: string | null
  // symbol overlay
  symbol: string | null
  // 위치
  anchorX: number
  anchorY: number
}
```

- 한 번에 하나의 오버레이만 표시
- 다른 마커/심볼 클릭 시 기존 오버레이 닫고 새 것 열기
- 같은 마커/심볼 재클릭 시 토글 (닫기)

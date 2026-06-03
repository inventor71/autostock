# Business Logic Model — Unit B: tui-components (TypeScript)

## BLM-1: 데이터 폴링 훅 (`useMonitorData`)

### 위치: `packages/tui-trading/src/hooks/use-monitor-data.ts`

```
훅: useMonitorData(steeringDir: string, intervalMs: number = 1500)

1. createSignal<MonitorData | null>(null)
2. setInterval로 steering/monitor.json 읽기 (fs.readFileSync)
3. JSON.parse → MonitorData 타입으로 캐스팅
4. 에러 시 이전 값 유지 (fail-safe)
5. onCleanup에서 clearInterval
6. 반환: { monitor, currentTurn, recentTurns, recentDecisions }
```

- 기존 `autostock.tsx` 사이드바의 폴링 패턴과 동일
- 향후 사이드바도 이 훅으로 리팩토링 가능

### 추가 훅: `useSnapshotData(steeringDir, intervalMs)`

기존 사이드바가 이미 snapshot.json을 폴링. 중복 방지를 위해:
- 동일 데이터를 두 번 읽지 않도록, 캐시된 시그널을 공유하거나
- 각각 독립 폴링 (1.5s 간격이면 부하 무시 가능)
- v1: 독립 폴링으로 시작, 필요 시 공유 레이어 추가

## BLM-2: 타임라인 바 컴포넌트 (`TimelineBar`)

### 위치: `packages/tui-trading/src/components/timeline-bar.tsx`

```
컴포넌트: TimelineBar(props: { width: number })

1. useMonitorData()로 모니터 데이터 구독
2. recentTurns를 시간순으로 정렬
3. 각 턴을 TimelineMarker로 변환:
   - glyph: 타입별 매핑 (research=●, intraday=○, wake=◆, eod=▲, reconcile=↻)
   - color: health별 (ok=타입색, error=red)
   - x: 시간 기반 가로 위치 (바 너비 내)
4. currentTurn이 있으면 "진행 중" 마커 추가 (깜빡임 효과: 0.5s 토글)
5. 렌더링:
   - 가로 1줄 높이의 박스
   - 시간 눈금 (09:30 -- 10:00 -- 10:30 -- ...)
   - 각 마커를 해당 x 위치에 배치
   - 현재 시점 표시 (→ now)
6. 마커 클릭 시 onMarkerClick(turnId) → 오버레이 상태 업데이트
```

### 마커 glyph 매핑
| type | glyph | 기본 색상 |
|------|-------|----------|
| research | ● | cyan |
| intraday | ○ | white |
| wake | ◆ | yellow |
| eod | ▲ | magenta |
| reconcile | ↻ | blue |
| (진행 중) | ◎ | green (깜빡임) |
| (에러) | ✕ | red |

### 시간축 계산
- 바 너비 = `props.width` (터미널 폭)
- 시간 범위: 09:00–16:30 (미국 장시간) 또는 첫 턴~마지막 턴+여백
- 각 턴의 `ts` (HH:MM)를 시간 범위 내 비율로 환산 → x 좌표
- 장 시간 외 턴(pre-market research)도 표시 (범위 자동 확장)

## BLM-3: 턴 오버레이 컴포넌트 (`TurnOverlay`)

### 위치: `packages/tui-trading/src/components/turn-overlay.tsx`

```
컴포넌트: TurnOverlay(props: { turnId: string, anchor: {x, y}, onClose: () => void })

1. useMonitorData()에서 해당 turnId의 턴 정보 찾기
2. 해당 turnId의 결정들 필터링
3. 렌더링 (플로팅 패널, Q3=A):
   - position="absolute", zIndex=2000
   - anchor 근처에 배치 (화면 경계 고려)
   - 턴 메타: [turnId] type | HH:MM | dur | $cost | N decisions
   - 요약: summary 텍스트
   - 결정 목록:
     - 각 결정: ACTION SYMBOL (confidence) reason...
     - 색상: BUY=green, SELL=red, HOLD=gray, ADJUST=yellow
     - 심볼 클릭 → 심볼 오버레이로 전환
   - 닫기: 패널 밖 클릭 또는 ESC
```

### 패널 크기
- 너비: 40-60 cols (내용에 따라)
- 높이: 턴 메타 2줄 + 결정 수 × 1줄 + 패딩 (최대 15줄, 스크롤)

## BLM-4: 심볼 오버레이 컴포넌트 (`SymbolOverlay`)

### 위치: `packages/tui-trading/src/components/symbol-overlay.tsx`

```
컴포넌트: SymbolOverlay(props: { symbol: string, anchor: {x, y}, onClose: () => void })

1. workspace/positions/SYMBOL.md 파일 읽기 (Q4=A, fs.readFileSync)
2. snapshot.json에서 해당 심볼의 포지션 정보 읽기
3. monitor decisions에서 해당 심볼의 최근 결정 필터링
4. 렌더링 (플로팅 패널):
   - position="absolute", zIndex=2000
   - 포지션 상태: qty | entry | current | P&L
   - thesis 내용: 마크다운 텍스트 (렌더링은 일반 텍스트로)
   - 최근 결정: 마지막 3-5개
   - 닫기: 패널 밖 클릭 또는 ESC
```

### 심볼 감지 범위
- **타임라인 오버레이 내**: 결정의 심볼 텍스트에 onMouseUp 핸들러
- **사이드바**: 기존 사이드바 심볼에 onMouseUp 핸들러 추가 (향후)
- **채팅**: v1에서는 미지원 (텍스트 내 심볼 파싱 복잡)

## BLM-5: 오버레이 상태 관리 (`createOverlayStore`)

### 위치: `packages/tui-trading/src/hooks/use-overlay.ts`

```
훅: createOverlayStore()

상태: OverlayState (E5)
- openTurn(turnId, anchorX, anchorY): 턴 오버레이 열기
- openSymbol(symbol, anchorX, anchorY): 심볼 오버레이 열기
- close(): 오버레이 닫기
- toggle(type, id, x, y): 같은 것 클릭 시 토글

규칙:
- 한 번에 하나의 오버레이만
- 턴 오버레이 내 심볼 클릭 → 턴 닫고 심볼 열기
- ESC 또는 패널 밖 클릭 → 닫기
```

## BLM-6: Session 레이아웃 수정 (`session_top` 슬롯)

### 위치: `packages/opencode/src/cli/cmd/tui/routes/session/index.tsx`

```
현재 레이아웃:
  <box flexDirection="column">
    <box flexDirection="row">
      <Sidebar />
      <scrollbox>(content)</scrollbox>
    </box>
    <Prompt />
  </box>

수정 후:
  <box flexDirection="column">
    <TuiPluginRuntime.Slot name="session_top" />  ← NEW
    <box flexDirection="row">
      <Sidebar />
      <scrollbox>(content)</scrollbox>
    </box>
    <Prompt />
  </box>
```

- `session_top` 슬롯은 타임라인 바 높이(1-2줄)만 차지
- 슬롯이 비어있으면 높이 0 (기존 동작 유지)
- `packages/tui-trading/`에서 이 슬롯에 `TimelineBar`를 등록

## BLM-7: 패키지 구조 (`packages/tui-trading/`)

```
packages/tui-trading/
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts              # 패키지 진입점 + 슬롯 등록
│   ├── types.ts              # MonitorData, MonitorTurn 등 타입
│   ├── hooks/
│   │   ├── use-monitor-data.ts   # monitor.json 폴링
│   │   ├── use-snapshot-data.ts  # snapshot.json 폴링 (심볼용)
│   │   ├── use-overlay.ts        # 오버레이 상태 관리
│   │   └── use-thesis.ts         # positions/SYMBOL.md 읽기
│   ├── components/
│   │   ├── timeline-bar.tsx      # 타임라인 바 (마커 + 시간축)
│   │   ├── turn-overlay.tsx      # 턴 상세 오버레이
│   │   ├── symbol-overlay.tsx    # 심볼 논거 오버레이
│   │   └── overlay-panel.tsx     # 공통 플로팅 패널 래퍼
│   └── utils/
│       ├── format.ts             # 포맷팅 유틸 (시간, 가격 등)
│       └── timeline-layout.ts    # 시간축 계산 로직
```

### 의존성
- `@opentui/solid` — UI 프리미티브 (`<box>`, `<text>`, 시그널 등)
- `@opentui/core` — 터미널 차원, 키맵
- `solid-js` — 반응형 프리미티브
- `fs` (Node 내장) — 파일 읽기

### 슬롯 등록 (`src/index.ts`)
```ts
TuiPluginRuntime.register("session_top", TimelineBar)
```
- opencode의 플러그인 로더가 이 패키지를 import
- 또는 Session 레이아웃에서 직접 `import { TimelineBar } from "@tui-trading"`

# F25 타임라인 바 개선 — Requirements

## 1. Market-Aware 시간대 (FR-1)

**현재**: `timeline-layout.ts`에 `MARKET_OPEN_MIN = 9*60+30`, `MARKET_CLOSE_MIN = 16*60`로 US Eastern 하드코딩.
한국 트레이더가 미장을 거래하므로 한국 시간 기준으로 타임라인이 잘못 표시됨.

**요구사항**:
- config/settings.yaml의 trading 설정에서 market open/close 시간을 읽어 타임라인에 반영
- daemon이 monitor.json에 `market_open`, `market_close` 필드를 추가해 TS 쪽에 전달
- 타임라인은 이 값을 기준으로 market hours 구간을 렌더링

## 2. 24시간 뷰 + 날짜 네비게이션 (FR-2)

**현재**: 현재시간 ± 여유분만큼의 range를 계산해 표시. 하루 전체를 보지 못하고, 이전 날짜 조회 불가.

**요구사항**:
- 하루 24시간(00:00-23:59)을 타임라인에 풀뷰로 표시
- Market hours 구간(market_open ~ market_close)을 배경색이나 강조선으로 시각적 구분
- 날짜 선택: 오늘(default), 이전/다음 날짜로 이동 가능 (좌우 화살표 또는 `<` `>` 버튼)
- 날짜 변경 시 해당 날짜의 턴 데이터를 daemon에 요청 (turns.jsonl의 date 필드 필터링)
- monitor.json에 `date` 파라미터 추가 또는 별도 API로 과거 데이터 조회

## 3. Human Intervention 마커 (FR-3)

**현재**: agent turn(research, intraday, wake, eod, reconcile)만 마커로 표시됨.
Human steering 명령(수동 매매, pause, flatten 등)은 `human_directives.jsonl`에 기록되지만 타임라인에 안 보임.

**요구사항**:
- `human_directives.jsonl`의 human intervention 이벤트를 타임라인 마커로 표시
- Human 마커는 agent turn 마커와 시각적으로 구분 (다른 glyph/색상)
- 마커 클릭 시 intervention 상세(command verb, symbol, 결과)를 overlay로 표시
- monitor.json에 `interventions` 블록 추가 (timestamp, verb, symbol, result)

## 데이터 흐름

```
daemon (Python)
  ├── turns.jsonl → monitor.json { turns: { recent: [...] } }         # FR-1, FR-2
  ├── human_directives.jsonl → monitor.json { interventions: [...] }   # FR-3
  ├── config/settings.yaml → monitor.json { market: { open, close } }  # FR-1
  └── date param → monitor.json date-filtered turns                    # FR-2

console TUI (TypeScript)
  ├── useMonitorData() → polling monitor.json
  ├── TimelineBar: 24h layout + market-hours highlight
  ├── intervention markers (new glyph: ✚ or ✎)
  └── date nav controls (< Today >)
```

## 관련 파일

| Layer | File | Change |
|-------|------|--------|
| TS | `timeline-layout.ts` | MARKET_OPEN/MARKET_CLOSE → monitor.json에서 동적 수신, 24h layout |
| TS | `timeline-bar.tsx` | market-hours highlight, intervention markers, date nav UI |
| TS | `types.ts` | `InterventionRecord`, `MarketHours` 타입 추가 |
| TS | `format.ts` | intervention glyph/color 추가 |
| Python | `runtime.py` | `_turns_summary`에 date 필터, interventions 블록, market hours 추가 |
| Python | `modes/agent.py` | market hours를 runtime에 주입 |
| Python | `commands.py` | intervention 발생 시 monitor 갱신 (또는 runtime이 polling) |

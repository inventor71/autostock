# F20 Functional Design — Business Logic Model

> Minimal depth. F20은 HTTP 클라이언트 + 포맷터로, 전통적인 도메인 비즈니스 로직 없음. "비즈니스 로직" = 데이터 흐름 파이프라인.

## 데이터 흐름 파이프라인

```
MCP Tool Call (opencode AI)
  │
  ▼
┌─ Zod Schema Validation ──────────────────────────────────┐
│ zod.parse(args) → typed params                           │
│ 실패 → throw (opencode MCP가 "invalid arguments"로 반환) │
└────────────────────┬─────────────────────────────────────┘
                     ▼
┌─ Auth Header Assembly ───────────────────────────┐
│ APCA-API-KEY-ID + APCA-API-SECRET (from process.env) │
│ 생성자에서 검증 완료, 이후 안전                    │
└────────────────────┬─────────────────────────────┘
                     ▼
┌─ HTTP GET (bun fetch, with timeout) ───────────────────┐
│ URL: {baseUrl}/v2/{endpoint}?{queryParams}        │
│ Headers: authHeaders                               │
│ Signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS)    │  ← F14 패턴 (alpaca_broker.py:72-73)
│ REQUEST_TIMEOUT_MS = 10_000 (10s, 전역 상수)        │     데몬: connect=3s, read=5s. TS는 단일 10s.
│ Method: GET only (never POST/PUT/DELETE)           │
└────────────────────┬─────────────────────────────┘
                     │
              ┌──────┴──────┐
              ▼              ▼
        HTTP 2xx          HTTP !2xx
              │              │
              ▼              ▼
┌─ Response Parsing ─┐  ┌─ Error Formatting ────────┐
│ resp.json()        │  │ 401 → "Authentication     │
│                    │  │   failed — check keys"     │
│                    │  │ 403 → "Access denied"      │
│                    │  │ 404 → "Not found: {id}"    │
│                    │  │ 429 → "Rate limited,       │
│                    │  │   retry after {n}s"        │
│                    │  │ 5xx → "Alpaca API error    │
│                    │  │   ({status}), retry later" │
└────────┬───────────┘  └───────────────────────────┘
         ▼
┌─ Markdown Formatting ───────────────────────────────────┐
│ formatTable() / formatBullets() / formatSnapshot()       │
│ ├─ 단일 객체 → 불릿 리스트 ("key: value")               │
│ ├─ 배열 → 마크다운 테이블 (헤더 + 행)                   │
│ ├─ 스냅샷 → 섹션 구분 (## subsection)                   │
│ ├─ Null/빈 배열 → "(no data)" 또는 "(no positions)"     │
│ └─ 대용량 → 최대 20행 + "... and N more"                │
└────────────────────┬─────────────────────────────────────┘
                     ▼
              MCP text response
```

## 포맷 분기 로직

```
formatResponse(data, method: string) → string
  │
  ├─ data === null || data === undefined
  │   → `(no data)`
  │
  ├─ Array.isArray(data)
  │   ├─ data.length === 0
  │   │   → context-aware message:
  │   │       "get_orders" → "(no orders found)"
  │   │       "get_all_positions" → "(no positions)"
  │   │       default → "(no results)"
  │   │
  │   └─ data.length > 0
  │       → formatTable(data, method)
  │           ├─ 첫 번째 항목의 키 → 테이블 헤더
  │           ├─ 각 항목 → 행 (중첩 객체는 JSON.stringify 축약)
  │           ├─ 20개 초과 → 앞 20개 + `\n... and {N-20} more`
  │           └─ 반환: markdown table string
  │
  └─ typeof data === "object" && !Array.isArray(data)
      ├─ method === "getStockSnapshot"
      │   → formatSnapshot(data)
      │       `## {symbol}\n### latest_trade\n{formatBullets(trade)}\n### latest_quote\n...`
      │
      └─ default
          → formatBullets(data)
              ├─ 최상위 키-값 쌍 → `- {key}: {value}`
              ├─ 중첩 객체 → 들여쓰기 `  - {subkey}: {subvalue}`
              └─ 배열 → `- {key}: [{length} items]` (요약)
```

## 메서드별 포맷 전략

| 메서드 | API 응답 형태 | 포맷 |
|--------|-------------|------|
| `getAccountInfo` | 단일 객체 | `formatBullets()` |
| `getAllPositions` | 배열 | `formatTable()` — 심볼, 수량, 시가, 손익 |
| `getOpenPosition` | 단일 객체 | `formatBullets()` — 상세 |
| `getPortfolioHistory` | 객체 (timestamp, equity, profit_loss 포함) | `formatBullets()` — 요약만, 시계열은 안내 |
| `getAsset` | 단일 객체 | `formatBullets()` |
| `getAllAssets` | 배열 | `formatTable()` — 심볼, 이름, 거래소, 상태 |
| `getCalendar` | 배열 | `formatTable()` — 날짜, open, close |
| `getMarketClock` | 단일 객체 | `formatBullets()` |
| `getOrders` | 배열 | `formatTable()` — id, 심볼, side, type, 상태, 수량 |
| `getStockBars` | 객체 `{symbols: {bars: [...]}}` | `## {symbol}\n` + `formatTable(bars)` |
| `getStockLatestBar` | 객체 `{symbol: {bar}}` | `formatTable()` — 심볼별 1행 |
| `getStockLatestQuote` | 객체 `{symbol: {quote}}` | `formatTable()` — 심볼, bid, ask, 사이즈 |
| `getStockLatestTrade` | 객체 `{symbol: {trade}}` | `formatTable()` — 심볼, 가격, 사이즈, 거래소, 시각 |
| `getStockQuote` | 객체 `{symbols: {quotes: [...]}}` | `## {symbol}\n` + `formatTable(quotes)` |
| `getStockSnapshot` | 객체 `{symbol: {latestTrade, latestQuote, minuteBar, dailyBar, previousDailyBar}}` | `formatSnapshot()` — 섹션 구분 |
| `getStockTrades` | 객체 `{symbols: {trades: [...]}}` | `## {symbol}\n` + `formatTable(trades)` |

## Fail-Fast: 생성자 검증

```typescript
constructor() {
  this.key = process.env.ALPACA_API_KEY;
  this.secret = process.env.ALPACA_API_SECRET;
  if (!this.key || !this.secret) {
    process.stderr.write("[autostock] ALPACA_API_KEY and ALPACA_API_SECRET must be set\n");
    process.exit(1);
  }
  this.authHeaders = {
    "APCA-API-KEY-ID": this.key,
    "APCA-API-SECRET-KEY": this.secret,
  };
}
```

- `process.exit(1)` → bun 프로세스 종료. opencode가 "MCP server disconnected"로 감지.
- stderr 메시지 → opencode 디버그 로그에 표시됨.
- 키 검증은 모듈 import 시점에 실행 (`const client = new AlpacaDataClient()`).

## Timeout 상수 (F14 패턴, alpaca_broker.py:72-73 대응)

```typescript
const REQUEST_TIMEOUT_MS = 10_000; // 10s. 데몬: connect=3s + read=5s. TS는 단일 초과시간.
```
- 모든 `fetch()` 호출에 `AbortSignal.timeout(REQUEST_TIMEOUT_MS)` 적용.
- timeout 발생 시 → `Alpaca API request timed out after 10s` 반환 (BR-2).

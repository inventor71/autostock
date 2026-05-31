# F20 Application Design — Component Methods

> 각 메서드는 Zod로 파라미터 검증 후 Alpaca API 호출 → JSON 응답 → 마크다운 텍스트 변환 → 반환.
> 상세 비즈니스 로직(포맷 규칙, 오류 코드별 분기 등)은 Construction — Functional Design에서 정의.

## C1. `AlpacaDataClient` 메서드 시그니처

### Constructor / Lifecycle

```typescript
constructor()
```
- `ALPACA_API_KEY` + `ALPACA_API_SECRET` env 검증.
- 없으면 `process.stderr.write("[autostock] ALPACA_API_KEY and ALPACA_API_SECRET must be set\n")` + `process.exit(1)`.
- 있으면 `authHeaders` 저장.

---

### Trading Read (paper-api.alpaca.markets)

#### `getAccountInfo() → Promise<string>`
- `GET /v2/account`
- 파라미터: 없음
- 반환: 불릿 리스트 — equity, cash, buying_power, portfolio_value, daytrade_count, pattern_day_trader, status 등

#### `getAllPositions() → Promise<string>`
- `GET /v2/positions`
- 파라미터: 없음
- 반환: 테이블 — `| symbol | qty | market_value | avg_entry_price | unrealized_pl | ... |`
- 빈 배열 → `(no positions)`

#### `getOpenPosition(symbol: string) → Promise<string>`
- `GET /v2/positions/{symbol}`
- 파라미터: `symbol: string` (Zod: non-empty, uppercase, alphanumeric + dots)
- 404 → `Position not found: {symbol}`
- 반환: 불릿 리스트 — 단일 포지션 상세

#### `getPortfolioHistory(params: PortfolioHistoryParams) → Promise<string>`
- `GET /v2/account/portfolio/history`
- 파라미터:
  ```typescript
  interface PortfolioHistoryParams {
    period?: string        // "1D"|"1W"|"1M"|"3M"|"6M"|"1A"|"5A"|"all"
    timeframe?: string     // "1Min"|"5Min"|"15Min"|"1H"|"1D"
    intraday_reporting?: string  // "market_hours"|"extended_hours"|"continuous"
  }
  ```
- 반환: 불릿 리스트 요약(timestamp, equity, profit_loss, base_value) + "시계열은 별도 bars 도구로 확인하세요" 안내

#### `getAsset(symbolOrId: string) → Promise<string>`
- `GET /v2/assets/{symbol_or_asset_id}`
- 파라미터: `symbolOrId: string`
- 반환: 불릿 리스트 — symbol, name, exchange, asset_class, status, tradable, marginable, etc.
- 404 → `Asset not found: {symbolOrId}`

#### `getAllAssets(params: AssetFilterParams) → Promise<string>`
- `GET /v2/assets`
- 파라미터:
  ```typescript
  interface AssetFilterParams {
    status?: string       // "active"|"inactive" (default: "active")
    asset_class?: string  // "us_equity"
    exchange?: string     // "NYSE"|"NASDAQ"|...
  }
  ```
- 반환: 테이블 (최대 50행 + `... and N more`)

#### `getCalendar(params: CalendarParams) → Promise<string>`
- `GET /v2/calendar`
- 파라미터:
  ```typescript
  interface CalendarParams {
    start?: string  // YYYY-MM-DD
    end?: string    // YYYY-MM-DD
  }
  ```
- 반환: 테이블 — `| date | open | close | session_open | session_close |`

#### `getMarketClock() → Promise<string>`
- `GET /v2/clock`
- 파라미터: 없음
- 반환: 불릿 리스트 — `timestamp`, `is_open`, `next_open`, `next_close`

#### `getOrders(params: OrderFilterParams) → Promise<string>`
- `GET /v2/orders`
- 파라미터:
  ```typescript
  interface OrderFilterParams {
    status?: string       // "open"|"closed"|"all" (default: "open")
    limit?: number        // 1..500
    after?: string        // ISO
    until?: string        // ISO
    direction?: string    // "asc"|"desc"
    symbol?: string
  }
  ```
- 반환: 테이블 — `| id | symbol | side | qty | type | status | filled_qty | created_at |`

---

### Stock Market Data (data.alpaca.markets)

#### `getStockBars(params: StockBarsParams) → Promise<string>`
- `GET /v2/stocks/{symbols}/bars`
- 파라미터:
  ```typescript
  interface StockBarsParams {
    symbol_or_symbols: string   // comma-separated
    timeframe: string           // "1Min"|"5Min"|"15Min"|"30Min"|"1Hour"|"1Day"
    start?: string              // ISO
    end?: string                // ISO
    limit?: number
    adjustment?: string         // "raw"|"split"|"dividend"|"all" (default: "raw")
  }
  ```
- 반환: 종목별 섹션 + 테이블 `| time | open | high | low | close | volume |`

#### `getStockLatestBar(symbols: string) → Promise<string>`
- `GET /v2/stocks/{symbols}/bars/latest`
- 파라미터: `symbols: string` (comma-separated)
- 반환: 테이블 `| symbol | time | open | high | low | close | volume |`

#### `getStockLatestQuote(symbols: string) → Promise<string>`
- `GET /v2/stocks/{symbols}/quotes/latest`
- 파라미터: `symbols: string`
- 반환: 테이블 `| symbol | bid | ask | bid_size | ask_size | timestamp |`

#### `getStockLatestTrade(symbols: string) → Promise<string>`
- `GET /v2/stocks/{symbols}/trades/latest`
- 파라미터: `symbols: string`
- 반환: 테이블 `| symbol | price | size | exchange | timestamp | conditions |`

#### `getStockQuote(params: StockQuoteParams) → Promise<string>`
- `GET /v2/stocks/{symbols}/quotes`
- 파라미터:
  ```typescript
  interface StockQuoteParams {
    symbol_or_symbols: string
    start?: string   // ISO
    end?: string     // ISO
    limit?: number
  }
  ```
- 반환: 종목별 테이블 (시계열 호가)

#### `getStockSnapshot(symbols: string) → Promise<string>`
- `GET /v2/stocks/{symbols}/snapshots`
- 파라미터: `symbols: string`
- 반환: 종목별 마크다운 섹션 — `## AAPL\n### latest_trade\n...\n### latest_quote\n...\n### minute_bar\n...\n### daily_bar\n...\n### previous_daily_bar\n...`

#### `getStockTrades(params: StockTradesParams) → Promise<string>`
- `GET /v2/stocks/{symbols}/trades`
- 파라미터:
  ```typescript
  interface StockTradesParams {
    symbol_or_symbols: string
    start?: string  // ISO
    end?: string    // ISO
    limit?: number
  }
  ```
- 반환: 종목별 테이블 (시계열 체결)

---

## C3. `mcp-server.ts` — 도구 등록 시그니처

각 도구는 기존 패턴 준수:
```typescript
server.registerTool(
  "<tool_name>",                       // Alpaca MCP exact name
  {
    description: "<one-line> (READ-ONLY).",
    inputSchema: { /* Zod flat object, 기존 F9 스타일 */ },
  },
  async (args) => txt(await client.<method>(args)),
);
```

16개 도구 → `client` 메서드 매핑:

| Tool | Client Method | InputSchema |
|------|---------------|-------------|
| `get_account_info` | `getAccountInfo()` | `{}` |
| `get_all_positions` | `getAllPositions()` | `{}` |
| `get_open_position` | `getOpenPosition(symbol)` | `{ symbol_or_asset_id: z.string() }` |
| `get_portfolio_history` | `getPortfolioHistory({period,timeframe,intraday_reporting})` | 선택적 3개 |
| `get_asset` | `getAsset(symbol_or_asset_id)` | `{ symbol_or_asset_id: z.string() }` |
| `get_all_assets` | `getAllAssets({status,asset_class,exchange})` | 선택적 3개 |
| `get_calendar` | `getCalendar({start,end})` | 선택적 2개 |
| `get_market_clock` | `getMarketClock()` | `{}` |
| `get_stock_bars` | `getStockBars({symbol_or_symbols,timeframe,...})` | `symbol_or_symbols: z.string()`, `timeframe: z.enum(...)`, 선택적 4개 |
| `get_stock_latest_bar` | `getStockLatestBar(symbol_or_symbols)` | `{ symbol_or_symbols: z.string() }` |
| `get_stock_latest_quote` | `getStockLatestQuote(symbol_or_symbols)` | `{ symbol_or_symbols: z.string() }` |
| `get_stock_latest_trade` | `getStockLatestTrade(symbol_or_symbols)` | `{ symbol_or_symbols: z.string() }` |
| `get_stock_quote` | `getStockQuote({symbol_or_symbols,start,end,limit})` | `symbol_or_symbols: z.string()`, 선택적 3개 |
| `get_stock_snapshot` | `getStockSnapshot(symbol_or_symbols)` | `{ symbol_or_symbols: z.string() }` |
| `get_stock_trades` | `getStockTrades({symbol_or_symbols,start,end,limit})` | `symbol_or_symbols: z.string()`, 선택적 3개 |
| `get_orders` | `getOrders({status,limit,after,until,direction,symbol})` | 선택적 6개 |

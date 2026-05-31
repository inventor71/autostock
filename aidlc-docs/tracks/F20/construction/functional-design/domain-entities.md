# F20 Functional Design — Domain Entities

> TypeScript 타입 정의. 도메인 모델이 아닌 API 파라미터/응답 타입. 모든 Zod schema는 이 타입에서 파생.

---

## Core Types

### AlpacaDataClient

```typescript
class AlpacaDataClient {
  private readonly key: string;
  private readonly secret: string;
  private readonly tradingBase: string; // "https://paper-api.alpaca.markets"
  private readonly dataBase: string;    // "https://data.alpaca.markets"

  constructor();  // fail-fast if key/secret missing

  // Trading Read (9 methods)
  getAccountInfo(): Promise<string>;
  getAllPositions(): Promise<string>;
  getOpenPosition(symbolOrAssetId: string): Promise<string>;
  getPortfolioHistory(params: PortfolioHistoryInput): Promise<string>;
  getAsset(symbolOrAssetId: string): Promise<string>;
  getAllAssets(params: AssetFilterInput): Promise<string>;
  getCalendar(params: CalendarInput): Promise<string>;
  getMarketClock(): Promise<string>;
  getOrders(params: OrderFilterInput): Promise<string>;

  // Stock Market Data (7 methods)
  getStockBars(params: StockBarsInput): Promise<string>;
  getStockLatestBar(symbolOrSymbols: string): Promise<string>;
  getStockLatestQuote(symbolOrSymbols: string): Promise<string>;
  getStockLatestTrade(symbolOrSymbols: string): Promise<string>;
  getStockQuote(params: StockQuoteInput): Promise<string>;
  getStockSnapshot(symbolOrSymbols: string): Promise<string>;
  getStockTrades(params: StockTradesInput): Promise<string>;
}
```

### Parameter Input Types (Zod → TypeScript)

```typescript
// No-param tools: getAccountInfo, getAllPositions, getMarketClock
// → no interface needed

interface PortfolioHistoryInput {
  period?:        "1D" | "1W" | "1M" | "3M" | "6M" | "1A" | "5A" | "all";
  timeframe?:     "1Min" | "5Min" | "15Min" | "1H" | "1D";
  intraday_reporting?: "market_hours" | "extended_hours" | "continuous";
}

interface AssetFilterInput {
  status?:     "active" | "inactive";
  asset_class?: "us_equity";
  exchange?:   string;
}

interface CalendarInput {
  start?: string;  // YYYY-MM-DD
  end?:   string;  // YYYY-MM-DD
}

interface OrderFilterInput {
  status?:     "open" | "closed" | "all";
  limit?:      number;   // 1..500
  after?:      string;   // ISO 8601
  until?:      string;   // ISO 8601
  direction?:  "asc" | "desc";
  symbol?:     string;
}

interface StockBarsInput {
  symbol_or_symbols: string;  // comma-separated
  timeframe:         "1Min" | "5Min" | "15Min" | "30Min" | "1Hour" | "1Day";
  start?:            string;  // ISO 8601
  end?:              string;  // ISO 8601
  limit?:            number;  // 1..10000
  adjustment?:       "raw" | "split" | "dividend" | "all";
}

interface StockQuoteInput {
  symbol_or_symbols: string;
  start?:  string;
  end?:    string;
  limit?:  number;
}

interface StockTradesInput extends StockQuoteInput {}
```

---

## Internal Helpers (not exported)

```typescript
// HTTP layer
function tradingGet(path: string, params?: Record<string, unknown>): Promise<unknown>;
function dataGet(path: string, params?: Record<string, unknown>): Promise<unknown>;
function buildUrl(base: string, path: string, params?: Record<string, unknown>): string;

// Formatting layer
function formatResponse(data: unknown, method: string): string;
function formatTable(rows: Record<string, unknown>[], method: string): string;
function formatBullets(obj: Record<string, unknown>, depth?: number): string;
function formatSnapshot(data: Record<string, unknown>): string;

// Field selection (BR-4)
function pickFields(obj: Record<string, unknown>, fields: string[]): Record<string, unknown>;
function formatCell(value: unknown): string;
```

---

## Error Type

```typescript
// F20 doesn't throw — all errors are formatted as strings
// The MCP tool handler always returns { content: [{ type: "text", text }] }
// Exception: constructor fail-fast via process.exit(1) — kills process, not throw
```

---

## Module Organization

```
operator-console/src/
├── alpaca-data.ts          # NEW: AlpacaDataClient + all helpers + Zod schemas
│   ├── class AlpacaDataClient (exported)
│   ├── Zod schemas (internal, not exported)
│   ├── tradingGet / dataGet (internal)
│   ├── formatTable / formatBullets / formatSnapshot / formatCell / pickFields (internal)
│   └── BR-2 error mapper (internal)
│
└── mcp-server.ts           # MODIFY: 16 registerTool calls
    ├── import { AlpacaDataClient } from "./alpaca-data"
    ├── const client = new AlpacaDataClient()  // fail-fast
    └── 16 × server.registerTool(...)          // cada tool → client method
```

---

## F21 Zod 통일성 참고

F21(`place_stock_order` arg robustness)도 Zod schema 검증을 다룸. 머지 시 확인할 항목:
- `symbol` 필드: F20은 `z.string().min(1).max(20)` vs F21의 symbol 검증 방식
- optional 필드 default 값 패턴
- `z.enum()` 값 목록 일관성 (timeframe, status, etc.)
- 둘 다 `mcp-server.ts` 경계에서 Zod 사용 → 통일된 패턴으로 리팩토링 기회

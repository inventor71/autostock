# F20 Application Design — Components

> 설계 범위: 신규 1개(`alpaca-data.ts`) + 기존 1개 수정(`mcp-server.ts`)

## 컴포넌트 목록

### C1. `AlpacaDataClient` (신규: `operator-console/src/alpaca-data.ts`)

**목적**: Alpaca REST API v2를 호출하여 시세·주문·포지션·계좌 데이터를 읽고, AI가 소비 가능한 마크다운 텍스트로 변환.

**책임**:
- 환경변수(`ALPACA_API_KEY`, `ALPACA_API_SECRET`)에서 자격증명 로드 및 검증 — 키 없으면 fail-fast(`process.exit(1)`)
- Alpaca Trading API(`paper-api.alpaca.markets`)와 Data API(`data.alpaca.markets`)로 GET 요청 수행
- Zod schema로 모든 파라미터 검증
- Alpaca JSON 응답 → 마크다운 테이블/불릿 리스트 텍스트로 변환 (FR-7)
- HTTP 오류(401/403/404/429/5xx) → 의미 있는 텍스트 오류 메시지 (NFR-4)

**인터페이스**:
```typescript
class AlpacaDataClient {
  constructor()
  // Trading read methods (10 endpoints)
  async getAccountInfo(): Promise<string>
  async getAllPositions(): Promise<string>
  async getOpenPosition(symbol: string): Promise<string>
  async getPortfolioHistory(params: PortfolioHistoryParams): Promise<string>
  async getAsset(symbolOrId: string): Promise<string>
  async getAllAssets(params: AssetFilterParams): Promise<string>
  async getCalendar(params: CalendarParams): Promise<string>
  async getMarketClock(): Promise<string>
  async getOrders(params: OrderFilterParams): Promise<string>
  // Data read methods (7 endpoints)
  async getStockBars(params: StockBarsParams): Promise<string>
  async getStockLatestBar(symbols: string): Promise<string>
  async getStockLatestQuote(symbols: string): Promise<string>
  async getStockLatestTrade(symbols: string): Promise<string>
  async getStockQuote(params: StockQuoteParams): Promise<string>
  async getStockSnapshot(symbols: string): Promise<string>
  async getStockTrades(params: StockTradesParams): Promise<string>
}
```

**내부 구조**:
| 모듈 요소 | 설명 |
|-----------|------|
| `ALPACA_KEY` / `ALPACA_SECRET` | 모듈 로드 시 `process.env`에서 읽고 검증. 없으면 stderr `[autostock]` 접두어 + `process.exit(1)`. |
| `ALPACA_PAPER` | env var `"true"` (default) → `paper-api.alpaca.markets`. `"false"` → `api.alpaca.markets`. 데몬 `BrokerConfig.paper: bool`과 대응. |
| `REQUEST_TIMEOUT_MS` | `10_000` (10s). F14 패턴 대응 (데몬: connect=3s + read=5s). 모든 fetch에 `AbortSignal.timeout()` 적용. |
| `authHeaders` | `{ "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret }` — 모든 요청에 포함 |
| `tradingGet(path, params?)` | `{paperBase}/v2/{path}` GET 요청. `ALPACA_PAPER`에 따라 엔드포인트 전환. |
| `dataGet(path, params?)` | `data.alpaca.markets/v2/{path}` GET 요청. 데이터 엔드포인트는 paper/live 동일. |
| `formatTable/formatBullets/formatKV` | JSON→마크다운 변환 유틸리티 (포맷터, C2에서 상세) |

### C2. `ResponseFormatter` (내부 유틸리티, `alpaca-data.ts` 내)

**목적**: Alpaca JSON 응답을 AI 친화적 마크다운으로 변환.

**책임**:
- 객체/배열 → 마크다운 테이블 변환 (필드 선택, 너무 긴 JSON 생략)
- 널/빈 응답 → 적절한 메시지 (`(no positions)`, `(no orders found)`)
- 타임스탬프를 사람이 읽을 수 있는 형식으로 유지 (ISO 8601 그대로)

**포맷 규칙**:
| 데이터 형태 | 출력 포맷 |
|-----------|----------|
| 단일 객체 (account, clock) | 불릿 리스트: `- equity: $12,345.67\n- cash: $5,000.00\n...` |
| 배열 (positions, orders, assets) | 마크다운 테이블: 헤더 + 행. 20개 초과 시 앞 20개 + `... and N more` |
| OHLCV (bars) | 마크다운 테이블: `\| time \| open \| high \| low \| close \| volume \|` |
| 스냅샷 (snapshot) | 섹션 구분: `## latest_trade\n...\n## latest_quote\n...\n## daily_bar\n...` |
| Null/빈 배열 | `(no data)` |

### C3. `mcp-server.ts` (기존 수정)

**변경 내용**:
- `alpaca-data.ts` import 추가
- `AlpacaDataClient` 싱글톤 인스턴스 생성 (모듈 로드 시 fail-fast 체크 포함)
- 16개 `registerTool` 호출 추가 — 기존 `steer`/`steer_read`/F9 도구 아래에 배치

**추가할 도구 등록 패턴** (기존 F9 패턴과 동일):
```typescript
server.registerTool(
  "get_stock_latest_trade",
  {
    description: "Get the latest trade for one or more stock symbols (READ-ONLY).",
    inputSchema: { symbol_or_symbols: z.string().describe("comma-separated symbols, e.g. AAPL,MSFT") },
  },
  async ({ symbol_or_symbols }) => txt(await client.getStockLatestTrade(symbol_or_symbols)),
);
```

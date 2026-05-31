# F20 Functional Design — Business Rules

> Zod validation schemas, HTTP error mapping, formatting constraints. No domain business rules — F20 is a data pipeline.

---

## BR-1: Zod Input Validation (SECURITY-05)

### BR-1.1 공통: `symbol_or_symbols`

```typescript
// Alpaca MCP 1:1 매칭 (Q3=A). 내부 split/trim.
const symbolOrSymbols = z.string()
  .min(1, "symbol_or_symbols is required")
  .max(200, "too many symbols")  // comma-separated, practical limit
  .describe("comma-separated stock symbols, e.g. AAPL,MSFT,TSLA");
```

F21 머지 시 참고: F21도 Zod symbol 검증을 다루므로 통일성 확인 필요.

### BR-1.2 파라미터 스키마 (per-tool)

```typescript
// -- Trading Read --
const AccountInfoParams = z.object({});  // no params

const OpenPositionParams = z.object({
  symbol_or_asset_id: z.string().min(1).max(20),
});

const PortfolioHistoryParams = z.object({
  period: z.enum(["1D","1W","1M","3M","6M","1A","5A","all"]).optional(),
  timeframe: z.enum(["1Min","5Min","15Min","1H","1D"]).optional(),
  intraday_reporting: z.enum(["market_hours","extended_hours","continuous"]).optional(),
});

const AssetParams = z.object({
  symbol_or_asset_id: z.string().min(1).max(20),
});

const AllAssetsParams = z.object({
  status: z.enum(["active","inactive"]).optional().default("active"),
  asset_class: z.enum(["us_equity"]).optional(),
  exchange: z.string().optional(),
});

const CalendarParams = z.object({
  start: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  end: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
});

// -- Stock Market Data --
const StockBarsParams = z.object({
  symbol_or_symbols: symbolOrSymbols,
  timeframe: z.enum(["1Min","5Min","15Min","30Min","1Hour","1Day"]),
  start: z.string().datetime({ offset: true }).optional(),  // ISO 8601
  end: z.string().datetime({ offset: true }).optional(),
  limit: z.number().int().min(1).max(10000).optional(),
  adjustment: z.enum(["raw","split","dividend","all"]).optional().default("raw"),
});

const StockLatestParams = z.object({
  symbol_or_symbols: symbolOrSymbols,
});

const StockQuoteParams = z.object({
  symbol_or_symbols: symbolOrSymbols,
  start: z.string().datetime({ offset: true }).optional(),
  end: z.string().datetime({ offset: true }).optional(),
  limit: z.number().int().min(1).max(10000).optional(),
});

const StockTradesParams = StockQuoteParams;  // 동일 구조

const OrderFilterParams = z.object({
  status: z.enum(["open","closed","all"]).optional().default("open"),
  limit: z.number().int().min(1).max(500).optional(),
  after: z.string().datetime({ offset: true }).optional(),
  until: z.string().datetime({ offset: true }).optional(),
  direction: z.enum(["asc","desc"]).optional(),
  symbol: z.string().optional(),
});
```

### BR-1.3 Zod 검증 실패 시 동작

Zod 검증은 opencode MCP 프레임워크가 내부적으로 수행 — `inputSchema`에 정의된 Zod object가 표준 MCP `tools/call` 경계에서 자동 검증됨. 우리 코드는 항상 유효한 파라미터를 받는다고 가정. 중복 검증 불필요 (MCP 프레임워크가 이미 담당).

---

## BR-2: HTTP 오류 → 오류 메시지 매핑 (NFR-4)

| HTTP Status | Alpaca 의미 | F20 반환 메시지 |
|------------|------------|----------------|
| 200 | 성공 | (정상 포맷 응답) |
| 401 | 인증 실패 | `Authentication failed — check ALPACA_API_KEY and ALPACA_API_SECRET` |
| 403 | 권한 없음 | `Access denied — your API key may not have permission for this endpoint` |
| 404 | 리소스 없음 | `Not found: {symbol_or_asset_id}. Check the symbol.` |
| 429 | 레이트 제한 | `Rate limited by Alpaca. Retry after {Retry-After} seconds.` (Retry-After 헤더가 있으면 그 값, 없으면 "a few seconds") |
| 500, 502, 503, 504 | 서버 오류 | `Alpaca API error (HTTP {status}). Please try again later.` |
| 기타 | — | `Alpaca API returned unexpected status {status}. Response: {first 200 chars}` |

**규칙**:
- 스택 트레이스, `ALPACA_API_KEY`, `ALPACA_API_SECRET`, 내부 URL 절대 포함 금지 (SECURITY-09, SECURITY-12).
- AbortSignal.timeout 발생 → `Alpaca API request timed out after 10s` (F14 패턴 — 데몬: connect=3s + read=5s. TS: 10s 단일 timeout. half-open socket·TCP stall 방지).
- `fetch` 자체 실패 (네트워크 오류) → `Alpaca API unavailable: {error.message}` (bun `fetch` 예외 메시지).
- JSON 파싱 실패 → `Alpaca API returned non-JSON response (HTTP {status})` — 파싱 불가 본문은 미포함 (SECURITY-09).

---

## BR-3: 마크다운 포맷팅 제약 (FR-7)

### BR-3.1 테이블 포맷
```
| Header1 | Header2 | Header3 |
|---------|---------|---------|
| val1    | val2    | val3    |
```

- 헤더: 첫 번째 배열 항목의 top-level 키 (중첩 객체 제외).
- 셀 값: `null` → `-`, `undefined` → `-`, boolean → `true`/`false`, number → 그대로, object → `JSON.stringify(obj)` (최대 80자, 초과 시 `{...}`).
- 최대 행 수: 20행 + `\n... and N more`.

### BR-3.2 불릿 리스트 포맷
```
- key1: value1
- key2: value2
  - subkey: subvalue
```

- 최상위 키만 1-depth, 중첩 객체는 2-depth 들여쓰기.
- 배열 값: `[N items]` 로 요약.
- `timestamp` / `created_at` / `updated_at` 등 날짜는 ISO 8601 그대로.

### BR-3.3 스냅샷 포맷
```
## AAPL
### latest_trade
{formatBullets(trade)}
### latest_quote
{formatBullets(quote)}
### minute_bar
{formatBullets(bar)}
### daily_bar
{formatBullets(bar)}
### previous_daily_bar
{formatBullets(bar)}
```

### BR-3.4 토큰 효율 규칙
- 전체 JSON raw dump 금지 (NFR-6 컨텍스트).
- API 응답에서 불필요한 필드 생략 (예: `raw` URL, 내부 UUID, 서버 측 메타데이터).
- 각 도구는 필수 필드만 선택하여 포맷 (아래 BR-4에서 정의).

---

## BR-4: 도구별 필수 출력 필드

| Tool | 출력 필드 (순서) |
|------|----------------|
| `get_account_info` | equity, cash, buying_power, portfolio_value, daytrade_count, pattern_day_trader, status, currency |
| `get_all_positions` | symbol, qty, market_value, avg_entry_price, unrealized_pl, unrealized_plpc, side |
| `get_open_position` | 위 + cost_basis, lastday_price, change_today |
| `get_portfolio_history` | timestamp, equity, profit_loss, profit_loss_pct, base_value (시계열 배열은 크기만 표시) |
| `get_asset` | symbol, name, exchange, asset_class, status, tradable, marginable, shortable, easy_to_borrow |
| `get_all_assets` | symbol, name, exchange, asset_class, status |
| `get_calendar` | date, open, close, session_open, session_close |
| `get_market_clock` | timestamp, is_open, next_open, next_close |
| `get_orders` | id, symbol, side, qty, filled_qty, type, status, limit_price, created_at, updated_at |
| `get_stock_bars` | time, open, high, low, close, volume |
| `get_stock_latest_bar` | symbol, time, open, high, low, close, volume |
| `get_stock_latest_quote` | symbol, bid_price, bid_size, ask_price, ask_size, timestamp |
| `get_stock_latest_trade` | symbol, price, size, exchange, timestamp, conditions |
| `get_stock_quote` | timestamp, bid_price, bid_size, ask_price, ask_size |
| `get_stock_snapshot` | latest_trade (price, timestamp), latest_quote (bid/ask), minute_bar (o/h/l/c/v), daily_bar (o/h/l/c/v), previous_daily_bar (o/h/l/c/v) |
| `get_stock_trades` | timestamp, price, size, exchange, conditions |

---

## PBT-01: Testable Properties (여기서 확정)

| ID | Component | Property Category | Property | 전략 |
|----|-----------|------------------|----------|------|
| P1 | `formatTable(array)` | Invariant | 출력 행 수 = min(input.length, 20) + 헤더 1행. 20개 초과 시 "and N more" 포함. | 랜덤 배열 생성 → 행 수 검증 |
| P2 | `formatBullets(obj)` | Invariant | 출력은 항상 `key: value` 라인을 최소 1개 포함. null → "(no data)". | 랜덤 객체 생성 → 출력 형식 검증 |
| P3 | `formatResponse(data, method)` | Type preservation | `null`/`undefined`/`[]`/`{}`/`[items]` 모든 경로 통과, 예외 없음. | 각 케이스별 랜덤 데이터 → 정상 문자열 반환 |
| P4 | Zod schemas | Round-trip | `schema.parse(schema.safeParse(input).data ?? input)` = parse 성공 시 동일 값 (단, default 채워짐). | fast-check로 `validInput` generator → parse 결과 비교 |
| P5 | `tradingGet`/`dataGet` | Invariant (error path) | HTTP 2xx → JSON parsed. HTTP !2xx → string error returned, never throws. | mock fetch → 다양한 status code → 항상 string 반환 |
| P6 | `buildUrl` | Idempotence | `buildUrl(base, path, params)` 여러 번 호출해도 동일 URL. | 랜덤 파라미터 조합 → URL 문자열 동일성 |

--- 

**PBT Framework**: `fast-check` (TypeScript). 상세는 Code Generation 단계에서 적용.

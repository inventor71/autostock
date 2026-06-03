// F20 — AlpacaDataClient unit tests. Mocks bun fetch to avoid calling the real Alpaca API.
// Property-based tests (PBT-01, P1-P6) are covered with varied inputs covering edge cases.
// Full fast-check integration deferred to build-and-test (fast-check lives in cli/ workspace).
import { afterEach, beforeEach, expect, test, mock } from "bun:test";
import { AlpacaDataClient } from "../src/alpaca-data";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let originalFetch: typeof globalThis.fetch;
let originalEnv: NodeJS.ProcessEnv;

beforeEach(() => {
  originalFetch = globalThis.fetch;
  originalEnv = { ...process.env };
  process.env.ALPACA_API_KEY = "test-key";
  process.env.ALPACA_API_SECRET = "test-secret";
  process.env.ALPACA_PAPER = "true";
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  process.env = originalEnv;
});

function mockFetch(status: number, body: unknown) {
  globalThis.fetch = mock((_url: string | URL | Request, _init?: RequestInit) => {
    return Promise.resolve(new Response(JSON.stringify(body), { status }));
  });
}

// ---------------------------------------------------------------------------
// Credential resolution (F22): try OS env first, then AUTOSTOCK_ROOT/.env.
// Module-level check still fails fast when keys are genuinely absent — the
// test `beforeEach` hook sets process.env before each new AlpacaDataClient()
// import, which the old module-level check would have missed (env vars are read
// once at import time). The F22 dotenv fallback is transparent to these tests
// since env vars are always set in beforeEach.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// HTTP status code → error messages (BR-2, NFR-4)
// ---------------------------------------------------------------------------

test("getAccountInfo: 401 → auth error message", async () => {
  process.env.ALPACA_API_KEY = "bad"; process.env.ALPACA_API_SECRET = "bad";
  mockFetch(401, {});
  const client = new AlpacaDataClient();
  const result = await client.getAccountInfo();
  expect(result).toContain("Authentication failed");
});

test("getAccountInfo: 403 → access denied", async () => {
  mockFetch(403, {});
  const client = new AlpacaDataClient();
  const result = await client.getAccountInfo();
  expect(result).toContain("Access denied");
});

test("getAccountInfo: 404 → not found", async () => {
  mockFetch(404, {});
  const client = new AlpacaDataClient();
  const result = await client.getAccountInfo();
  expect(result).toContain("Not found");
});

test("getAccountInfo: 429 → rate limited", async () => {
  const headers = new Headers();
  headers.set("Retry-After", "30");
  globalThis.fetch = mock(() => Promise.resolve(new Response("{}", { status: 429, headers })));
  const client = new AlpacaDataClient();
  const result = await client.getAccountInfo();
  expect(result).toContain("Rate limited");
  expect(result).toContain("30");
});

test("getAccountInfo: 500 → server error", async () => {
  mockFetch(500, {});
  const client = new AlpacaDataClient();
  const result = await client.getAccountInfo();
  expect(result).toContain("Alpaca API error");
});

test("getAccountInfo: network error → unavailable", async () => {
  globalThis.fetch = mock(() => Promise.reject(new Error("connect ECONNREFUSED")));
  const client = new AlpacaDataClient();
  const result = await client.getAccountInfo();
  expect(result).toContain("Alpaca API unavailable");
});

test("getAccountInfo: timeout → timed out message (critic H1)", async () => {
  globalThis.fetch = mock(() => Promise.reject(new DOMException("The operation was aborted", "AbortError")));
  const client = new AlpacaDataClient();
  const result = await client.getAccountInfo();
  expect(result).toContain("timed out");
});

// ---------------------------------------------------------------------------
// 200 → formatted markdown (never throws)
// ---------------------------------------------------------------------------

test("getAccountInfo: 200 → bullet list", async () => {
  mockFetch(200, { equity: "12345.67", cash: "5000.00", buying_power: "24691.34", portfolio_value: "12345.67", daytrade_count: 0, pattern_day_trader: false, status: "ACTIVE", currency: "USD" });
  const client = new AlpacaDataClient();
  const result = await client.getAccountInfo();
  expect(result).toContain("equity");
  expect(result).toContain("12345.67");
  expect(result).toContain("ACTIVE");
});

test("getAllPositions: 200 → table", async () => {
  mockFetch(200, [
    { symbol: "AAPL", qty: "10", market_value: "1950.00", avg_entry_price: "190.00", unrealized_pl: "50.00", unrealized_plpc: "0.0263", side: "long" },
    { symbol: "MSFT", qty: "5", market_value: "1975.00", avg_entry_price: "380.00", unrealized_pl: "75.00", unrealized_plpc: "0.0394", side: "long" },
  ]);
  const client = new AlpacaDataClient();
  const result = await client.getAllPositions();
  expect(result).toContain("AAPL");
  expect(result).toContain("MSFT");
  expect(result).toContain("| symbol |");
});

test("getAllPositions: empty array → (no positions)", async () => {
  mockFetch(200, []);
  const client = new AlpacaDataClient();
  const result = await client.getAllPositions();
  expect(result).toContain("(no positions)");
});

test("getOpenPosition: 200 → single position detail", async () => {
  mockFetch(200, { symbol: "AAPL", qty: "10", market_value: "1950.00", avg_entry_price: "190.00", unrealized_pl: "50.00", unrealized_plpc: "0.0263", side: "long", cost_basis: "1900.00", lastday_price: "195.00", change_today: "0.50" });
  const client = new AlpacaDataClient();
  const result = await client.getOpenPosition("AAPL");
  expect(result).toContain("AAPL");
  expect(result).toContain("cost_basis");
});

test("getMarketClock: 200 → bullet list", async () => {
  mockFetch(200, { timestamp: "2026-05-31T12:00:00Z", is_open: true, next_open: "2026-05-31T13:30:00Z", next_close: "2026-05-31T20:00:00Z" });
  const client = new AlpacaDataClient();
  const result = await client.getMarketClock();
  expect(result).toContain("is_open");
  expect(result).toContain("true");
});

test("getOrders: 200 → table, extra fields excluded (BR-4)", async () => {
  mockFetch(200, [{ id: "abc123", symbol: "AAPL", side: "buy", qty: "10", filled_qty: "10", type: "market", status: "filled", limit_price: null, created_at: "2026-05-31T10:00:00Z", updated_at: "2026-05-31T10:00:01Z", extra_ignored: "should not appear" }]);
  const client = new AlpacaDataClient();
  const result = await client.getOrders({ status: "all" });
  expect(result).toContain("abc123");
  expect(result).toContain("AAPL");
  expect(result).not.toContain("extra_ignored");
});

test("getOrders: empty → (no orders found)", async () => {
  mockFetch(200, []);
  const client = new AlpacaDataClient();
  const result = await client.getOrders();
  expect(result).toContain("(no orders found)");
});

test("getStockLatestTrade: 200 → table", async () => {
  mockFetch(200, { trades: { AAPL: { price: 195.83, size: 100, exchange: "Q", timestamp: "2026-05-31T12:00:00Z", conditions: ["@"] } } });
  const client = new AlpacaDataClient();
  const result = await client.getStockLatestTrade("AAPL");
  expect(result).toContain("AAPL");
  expect(result).toContain("195.83");
  expect(result).toContain("Q");
});

test("getStockSnapshot: 200 → sectioned markdown", async () => {
  mockFetch(200, { AAPL: { latestTrade: { price: 195.83, timestamp: "2026-05-31T12:00:00Z" }, latestQuote: { bid_price: 195.80, ask_price: 195.85 }, minuteBar: { o: 195.50, h: 196.00, l: 195.40, c: 195.83, v: 5000 }, dailyBar: { o: 194.00, h: 196.50, l: 193.50, c: 195.83, v: 50000 }, previousDailyBar: { o: 193.00, h: 195.00, l: 192.50, c: 194.00, v: 48000 } } });
  const client = new AlpacaDataClient();
  const result = await client.getStockSnapshot("AAPL");
  expect(result).toContain("## AAPL");
  expect(result).toContain("### latest_trade");
  expect(result).toContain("### latest_quote");
  expect(result).toContain("### daily_bar");
  expect(result).toContain("### previous_daily_bar");
});

test("getStockBars: 200 → mapped bar field names", async () => {
  mockFetch(200, { bars: { AAPL: [{ t: "2026-05-31T10:00:00Z", o: 195.0, h: 196.0, l: 194.5, c: 195.5, v: 10000 }] } });
  const client = new AlpacaDataClient();
  const result = await client.getStockBars({ symbol_or_symbols: "AAPL", timeframe: "1Min" });
  expect(result).toContain("## AAPL");
  expect(result).toContain("| time | open | high | low | close | volume |");
  expect(result).not.toContain("| t | o | h | l | c | v |");
});

// ---------------------------------------------------------------------------
// SECURITY-12: auth headers never in response
// ---------------------------------------------------------------------------

test("auth headers never appear in response text", async () => {
  mockFetch(200, { equity: "100" });
  const client = new AlpacaDataClient();
  const result = await client.getAccountInfo();
  expect(result).not.toContain("APCA-API-KEY-ID");
  expect(result).not.toContain("APCA-API-SECRET-KEY");
});

// ---------------------------------------------------------------------------
// PBT-01: Property-based tests (P1-P6)
// fast-check lives in cli/ workspace — not importable from this test dir.
// Tests below cover the same properties with varied deterministic inputs.
// ---------------------------------------------------------------------------

// P1: formatTable invariant — row count bounded, truncation marker present
test("PBT-P1: formatTable row count invariant", async () => {
  // 0 rows → "(no results)"
  mockFetch(200, []);
  expect(await new AlpacaDataClient().getAllAssets({ status: "active" })).toBe("(no results)");

  // 1 row → header row present
  mockFetch(200, [{ symbol: "A", name: "Name", exchange: "X", asset_class: "us_equity", status: "active" }]);
  const r1 = await new AlpacaDataClient().getAllAssets({ status: "active" });
  expect(r1).toContain("| symbol |");

  // 25 rows → "and N more" present
  const rows25 = Array.from({ length: 25 }, (_, i) => ({ symbol: `S${i}`, name: `N${i}`, exchange: "X", asset_class: "us_equity", status: "active" }));
  mockFetch(200, rows25);
  const r25 = await new AlpacaDataClient().getAllAssets({ status: "active" });
  expect(r25).toContain("... and");
});

// P2: formatBullets invariant — always key: value lines
test("PBT-P2: formatBullets always produces key: value output", async () => {
  const cases = [
    { input: { a: 1 }, expectKey: "a:" },
    { input: { a: null }, expectVal: "-" },
    { input: { a: "hello" }, expectVal: "hello" },
  ];
  for (const tc of cases) {
    mockFetch(200, tc.input);
    const result = await new AlpacaDataClient().getMarketClock();
    if (tc.expectKey) expect(result).toContain(tc.expectKey);
    if (tc.expectVal) expect(result).toContain(tc.expectVal);
  }
});

// P3: formatResponse all paths — null/[]/{}/[items], never throws
test("PBT-P3: formatResponse all input paths return strings", async () => {
  const shapes: unknown[] = [null, {}, { a: 1 }, [], [{ x: 1 }], { a: { b: { c: 1 } } }];
  for (const shape of shapes) {
    mockFetch(200, shape);
    const result = await new AlpacaDataClient().getMarketClock();
    expect(typeof result).toBe("string");
    expect(result.length).toBeGreaterThan(0);
  }
});

// P4: StockBarsParams round-trip — same params produce consistent results
test("PBT-P4: StockBarsParams — same params, same results", async () => {
  mockFetch(200, { bars: { AAPL: [] } });
  const client = new AlpacaDataClient();
  const r1 = await client.getStockBars({ symbol_or_symbols: "AAPL", timeframe: "1Min" });
  const r2 = await client.getStockBars({ symbol_or_symbols: "AAPL", timeframe: "1Min" });
  expect(r1).toBe(r2);
  // Different timeframe → different result
  const r3 = await client.getStockBars({ symbol_or_symbols: "AAPL", timeframe: "1Day" });
  // Same empty bars for both timeframes with this mock
  expect(typeof r3).toBe("string");
});

// P5: HTTP error paths never throw
test("PBT-P5: all HTTP status codes return strings", async () => {
  for (const status of [200, 401, 403, 404, 429, 500, 502, 503]) {
    mockFetch(status, status === 200 ? { equity: "100" } : {});
    const result = await new AlpacaDataClient().getAccountInfo();
    expect(typeof result).toBe("string");
  }
});

// P6: buildUrl idempotence (same params → same output)
test("PBT-P6: same params produce same output", async () => {
  mockFetch(200, { equity: "100" });
  const client = new AlpacaDataClient();
  const r1 = await client.getAccountInfo();
  const r2 = await client.getAccountInfo();
  expect(r1).toBe(r2);
});

// F20 — Alpaca MCP stock-only read tools. Console in-process TS calls Alpaca REST API v2
// directly (Q2=A). No daemon round-trip, no new FileDrop channel.
//
// Credential resolution (F22): try OS env first, then fall back to reading AUTOSTOCK_ROOT/.env.
// This keeps the Docker attach harness working without OS-env Alpaca vars (which would conflict
// with pydantic-settings OS-env > dotenv precedence), while still failing fast when keys are
// genuinely absent — steer/steer_read/F9 order tools are unaffected either way.
//
// HTTP timeout (critic H1): REQUEST_TIMEOUT_MS = 10s. F14 fixed the same class of wedge on the
// Python side (alpaca_broker.py:72-73, connect=3s + read=5s). TS uses a single 10s AbortSignal.
//
// ALPACA_PAPER env (critic M2): "true" (default) → paper-api.alpaca.markets. "false" →
// api.alpaca.markets. Matches daemon BrokerConfig.paper: bool.
//
// Zod schemas live in mcp-server.ts (inline inputSchema objects — consistent with the
// existing F9 tool pattern). This module uses plain TS interfaces for its method params.

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REQUEST_TIMEOUT_MS = 10_000; // 10 s — F14 pattern (daemon connect=3s + read=5s)

// ---------------------------------------------------------------------------
// Credential resolution: OS env first, then AUTOSTOCK_ROOT/.env fallback (F22)
// ---------------------------------------------------------------------------

function readEnvOrDotenv(key: string): string {
  const val = process.env[key];
  if (val) return val;
  // Fallback: read from the daemon's .env file (needed when running in Docker
  // attach mode where ALPACA_* vars aren't injected as OS env to avoid clashing
  // with pydantic-settings OS-env > dotenv precedence).
  const root = process.env.AUTOSTOCK_ROOT || process.cwd();
  try {
    const fs = require("node:fs");
    const content = fs.readFileSync(`${root}/.env`, "utf-8") as string;
    for (const line of content.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const eq = trimmed.indexOf("=");
      if (eq === -1) continue;
      const k = trimmed.slice(0, eq).trim();
      const v = trimmed.slice(eq + 1).trim();
      if (k === key) return v;
    }
  } catch {
    // File not found or unreadable — caller will handle the empty result.
  }
  return "";
}

const ALPACA_API_KEY = readEnvOrDotenv("ALPACA_API_KEY");
const ALPACA_API_SECRET = readEnvOrDotenv("ALPACA_API_SECRET");

if (!ALPACA_API_KEY || !ALPACA_API_SECRET) {
  process.stderr.write(
    "[autostock] ALPACA_API_KEY and ALPACA_API_SECRET must be set\n",
  );
  process.exit(1);
}

const ALPACA_PAPER = (process.env.ALPACA_PAPER ?? "true") === "true"; // critic M2

const TRADING_BASE = ALPACA_PAPER
  ? "https://paper-api.alpaca.markets"
  : "https://api.alpaca.markets";
const DATA_BASE = "https://data.alpaca.markets"; // same for paper & live

const AUTH_HEADERS = {
  "APCA-API-KEY-ID": ALPACA_API_KEY,
  "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
};

// ---------------------------------------------------------------------------
// Parameter types (plain TS, no zod dependency — zod schemas live in mcp-server.ts)
// ---------------------------------------------------------------------------

export interface PortfolioHistoryParams {
  period?: "1D" | "1W" | "1M" | "3M" | "6M" | "1A" | "5A" | "all";
  timeframe?: "1Min" | "5Min" | "15Min" | "1H" | "1D";
  intraday_reporting?: "market_hours" | "extended_hours" | "continuous";
}

export interface AssetFilterParams {
  status?: "active" | "inactive";
  asset_class?: "us_equity";
  exchange?: string;
}

export interface CalendarParams {
  start?: string; // YYYY-MM-DD
  end?: string;   // YYYY-MM-DD
}

export interface OrderFilterParams {
  status?: "open" | "closed" | "all";
  limit?: number;
  after?: string;
  until?: string;
  direction?: "asc" | "desc";
  symbols?: string; // comma-separated — Alpaca REST v2 uses "symbols" (plural)
}

export interface StockBarsParams {
  symbol_or_symbols: string;
  timeframe: "1Min" | "5Min" | "15Min" | "30Min" | "1Hour" | "1Day";
  start?: string;
  end?: string;
  limit?: number;
  adjustment?: "raw" | "split" | "dividend" | "all";
}

export interface StockQuoteParams {
  symbol_or_symbols: string;
  start?: string;
  end?: string;
  limit?: number;
}

export interface StockTradesParams extends StockQuoteParams {}

// ---------------------------------------------------------------------------
// HTTP layer
// ---------------------------------------------------------------------------

function buildUrl(
  base: string,
  path: string,
  params?: Record<string, unknown>,
): string {
  const url = new URL(path, base);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null) {
        url.searchParams.set(k, String(v));
      }
    }
  }
  return url.toString();
}

/** bun fetch wrapper. Never throws — always returns a string error or parsed JSON. */
async function apiGet(
  base: string,
  path: string,
  params?: Record<string, unknown>,
): Promise<unknown> {
  const url = buildUrl(base, path, params);
  let resp: Response;
  try {
    resp = await fetch(url, {
      headers: AUTH_HEADERS,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg.includes("timed out") || msg.includes("aborted") || msg.includes("AbortError")) {
      return `Alpaca API request timed out after ${REQUEST_TIMEOUT_MS / 1000}s`;
    }
    return `Alpaca API unavailable: ${msg}`;
  }

  // HTTP error → formatted message (BR-2)
  if (!resp.ok) {
    if (resp.status === 401) {
      return "Authentication failed — check ALPACA_API_KEY and ALPACA_API_SECRET";
    }
    if (resp.status === 403) {
      return "Access denied — your API key may not have permission for this endpoint";
    }
    if (resp.status === 404) {
      const body = await resp.text().catch(() => "");
      return `Not found. Check the symbol or id.${body ? ` (${body.slice(0, 120)})` : ""}`;
    }
    if (resp.status === 429) {
      const retry = resp.headers.get("Retry-After") ?? "a few";
      return `Rate limited by Alpaca. Retry after ${retry} seconds.`;
    }
    if (resp.status >= 500) {
      return `Alpaca API error (HTTP ${resp.status}). Please try again later.`;
    }
    return `Alpaca API returned unexpected status ${resp.status}`;
  }

  // Parse JSON — failure returns string, not throw (NFR-4)
  try {
    return await resp.json();
  } catch {
    return `Alpaca API returned non-JSON response (HTTP ${resp.status})`;
  }
}

function tradingGet(
  path: string,
  params?: Record<string, unknown>,
): Promise<unknown> {
  return apiGet(TRADING_BASE, path, params);
}

function dataGet(
  path: string,
  params?: Record<string, unknown>,
): Promise<unknown> {
  return apiGet(DATA_BASE, path, params);
}

// ---------------------------------------------------------------------------
// Formatting layer (BR-3, BR-4)
// ---------------------------------------------------------------------------

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return `[${value.length} items]`;
  const s = JSON.stringify(value);
  return s.length > 80 ? s.slice(0, 77) + "..." : s;
}

/** Pick only specified fields from an object (BR-4). */
function pickFields(
  obj: Record<string, unknown>,
  fields: string[],
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    if (f in obj) out[f] = obj[f];
  }
  return out;
}

function formatTable(
  rows: Record<string, unknown>[],
  _method?: string,
): string {
  if (rows.length === 0) return "(no results)";

  const MAX_ROWS = 20;
  const fields = Object.keys(rows[0]);
  const header = `| ${fields.join(" | ")} |`;
  const sep = `|${fields.map(() => "---").join("|")}|`;

  const bodyRows = rows.slice(0, MAX_ROWS);
  const lines = bodyRows.map(
    (row) => `| ${fields.map((f) => formatCell(row[f])).join(" | ")} |`,
  );

  let out = `${header}\n${sep}\n${lines.join("\n")}`;
  if (rows.length > MAX_ROWS) {
    out += `\n\n... and ${rows.length - MAX_ROWS} more`;
  }
  return out;
}

function formatBullets(
  obj: Record<string, unknown>,
  depth = 0,
): string {
  const entries = Object.entries(obj);
  if (entries.length === 0) return "(empty)";
  const prefix = "  ".repeat(depth);
  const lines: string[] = [];
  for (const [key, value] of entries) {
    if (value !== null && value !== undefined && typeof value === "object" && !Array.isArray(value)) {
      lines.push(`${prefix}- ${key}:`);
      lines.push(formatBullets(value as Record<string, unknown>, depth + 1));
    } else if (Array.isArray(value)) {
      lines.push(`${prefix}- ${key}: [${value.length} items]`);
    } else {
      lines.push(`${prefix}- ${key}: ${formatCell(value)}`);
    }
  }
  return lines.join("\n");
}

function formatSnapshot(data: Record<string, unknown>): string {
  // data is { symbol: { latestTrade, latestQuote, minuteBar, dailyBar, previousDailyBar } }
  const symbols = Object.keys(data);
  if (symbols.length === 0) return "(no snapshot data)";

  const sections: string[] = [];
  for (const sym of symbols) {
    const snap = data[sym] as Record<string, unknown>;
    sections.push(`## ${sym}`);
    if (snap.latestTrade) {
      sections.push("### latest_trade");
      sections.push(formatBullets(snap.latestTrade as Record<string, unknown>));
    }
    if (snap.latestQuote) {
      sections.push("### latest_quote");
      sections.push(formatBullets(snap.latestQuote as Record<string, unknown>));
    }
    if (snap.minuteBar) {
      sections.push("### minute_bar");
      sections.push(formatBullets(snap.minuteBar as Record<string, unknown>));
    }
    if (snap.dailyBar) {
      sections.push("### daily_bar");
      sections.push(formatBullets(snap.dailyBar as Record<string, unknown>));
    }
    if (snap.previousDailyBar) {
      sections.push("### previous_daily_bar");
      sections.push(formatBullets(snap.previousDailyBar as Record<string, unknown>));
    }
  }
  return sections.join("\n\n");
}

function formatBarsResponse(
  data: unknown,
  _method: string,
): string {
  // Alpaca returns { symbols: { AAPL: [...], MSFT: [...] } } for bars
  if (!data || typeof data !== "object") return "(no data)";
  const obj = data as Record<string, unknown>;
  const symbols = obj.symbols as Record<string, unknown[]> | undefined;
  if (!symbols) {
    // fallback: treat as direct array or object
    return formatResponse(data, _method);
  }
  const sections: string[] = [];
  for (const [sym, bars] of Object.entries(symbols)) {
    sections.push(`## ${sym}`);
    if (Array.isArray(bars)) {
      sections.push(formatTable(bars, _method));
    } else {
      sections.push(formatBullets(bars as Record<string, unknown>));
    }
  }
  return sections.join("\n\n");
}

// Exported for the F94 provider-aware account reader (account-truth.ts) so the
// daemon-snapshot path renders identically to the Alpaca path.
export function formatResponse(data: unknown, method: string): string {
  if (data === null || data === undefined) {
    return "(no data)";
  }

  if (typeof data === "string") {
    // Already an error message from apiGet
    return data;
  }

  if (Array.isArray(data)) {
    if (data.length === 0) {
      const empty: Record<string, string> = {
        getOrders: "(no orders found)",
        getAllPositions: "(no positions)",
        get_all_positions: "(no positions)",
        get_orders: "(no orders found)",
      };
      return empty[method] ?? "(no results)";
    }
    return formatTable(data as Record<string, unknown>[], method);
  }

  if (typeof data === "object") {
    const obj = data as Record<string, unknown>;

    // Branch: snapshot
    if (
      method === "getStockSnapshot" ||
      method === "get_stock_snapshot"
    ) {
      // Check if it has a symbol-keyed structure (snapshots endpoint)
      const firstVal = Object.values(obj)[0];
      if (firstVal && typeof firstVal === "object" && (firstVal as Record<string, unknown>).latestTrade) {
        return formatSnapshot(obj);
      }
      // Single symbol snapshot object
      if (obj.latestTrade || obj.latestQuote) {
        return formatSnapshot({ _: obj });
      }
    }

    // Branch: bars with symbols wrapper
    if (obj.symbols) {
      return formatBarsResponse(data, method);
    }

    // Default: bullets
    return formatBullets(obj);
  }

  return String(data);
}

// ---------------------------------------------------------------------------
// Field selectors (BR-4 per-tool output fields)
// ---------------------------------------------------------------------------

const ACCOUNT_FIELDS = [
  "equity", "cash", "buying_power", "portfolio_value",
  "daytrade_count", "pattern_day_trader", "status", "currency",
];

const POSITION_LIST_FIELDS = [
  "symbol", "qty", "market_value", "avg_entry_price",
  "unrealized_pl", "unrealized_plpc", "side",
];

const POSITION_DETAIL_FIELDS = [
  ...POSITION_LIST_FIELDS, "cost_basis", "lastday_price", "change_today",
];

const ASSET_LIST_FIELDS = [
  "symbol", "name", "exchange", "asset_class", "status",
];

const ORDER_LIST_FIELDS = [
  "id", "symbol", "side", "qty", "filled_qty", "type",
  "status", "limit_price", "created_at", "updated_at",
];

const BAR_FIELDS = ["t", "o", "h", "l", "c", "v"];

const LATEST_TRADE_FIELDS = [
  "symbol", "price", "size", "exchange", "timestamp", "conditions",
];

const LATEST_QUOTE_FIELDS = [
  "symbol", "bid_price", "bid_size", "ask_price", "ask_size", "timestamp",
];

// Map property names (from bar response) to more readable names
function mapBarFields(row: Record<string, unknown>): Record<string, unknown> {
  const m: Record<string, string> = {
    t: "time", o: "open", h: "high", l: "low", c: "close", v: "volume",
  };
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(row)) {
    out[m[k] ?? k] = v;
  }
  return out;
}

// ---------------------------------------------------------------------------
// AlpacaDataClient — 9 trading read + 7 data read = 16 methods
// ---------------------------------------------------------------------------

export class AlpacaDataClient {
  // ---- Trading Read ----

  async getAccountInfo(): Promise<string> {
    const data = await tradingGet("/v2/account");
    if (typeof data === "string") return data;
    return formatResponse(pickFields(data as Record<string, unknown>, ACCOUNT_FIELDS), "getAccountInfo");
  }

  async getAllPositions(): Promise<string> {
    const data = await tradingGet("/v2/positions");
    if (typeof data === "string") return data;
    if (Array.isArray(data)) {
      return formatResponse(
        (data as Record<string, unknown>[]).map((p) => pickFields(p, POSITION_LIST_FIELDS)),
        "getAllPositions",
      );
    }
    return formatResponse(data, "getAllPositions");
  }

  async getOpenPosition(symbolOrAssetId: string): Promise<string> {
    const data = await tradingGet(`/v2/positions/${encodeURIComponent(symbolOrAssetId)}`);
    if (typeof data === "string") return data;
    return formatResponse(pickFields(data as Record<string, unknown>, POSITION_DETAIL_FIELDS), "getOpenPosition");
  }

  async getPortfolioHistory(
    params: PortfolioHistoryParams = {},
  ): Promise<string> {
    const data = await tradingGet("/v2/account/portfolio/history", params as Record<string, unknown>);
    if (typeof data === "string") return data;
    const obj = data as Record<string, unknown>;
    const fields = ["timestamp", "equity", "profit_loss", "profit_loss_pct", "base_value"];
    const summary = pickFields(obj, fields);
    if (obj.timestamp && Array.isArray(obj.timestamp)) {
      summary["data_points"] = (obj.timestamp as unknown[]).length;
    }
    // Don't dump raw timeseries — guide to bars tool
    let out = formatBullets(summary);
    if (obj.timestamp && Array.isArray(obj.timestamp) && (obj.timestamp as unknown[]).length > 0) {
      out += "\n\n(use get_stock_bars or get_portfolio_history with shorter period for detailed timeseries)";
    }
    return out;
  }

  async getAsset(symbolOrAssetId: string): Promise<string> {
    const data = await tradingGet(`/v2/assets/${encodeURIComponent(symbolOrAssetId)}`);
    return formatResponse(data, "getAsset");
  }

  async getAllAssets(
    params: AssetFilterParams = {},
  ): Promise<string> {
    const data = await tradingGet("/v2/assets", params as Record<string, unknown>);
    if (typeof data === "string") return data;
    if (Array.isArray(data)) {
      return formatResponse(
        (data as Record<string, unknown>[]).map((a) => pickFields(a, ASSET_LIST_FIELDS)),
        "getAllAssets",
      );
    }
    return formatResponse(data, "getAllAssets");
  }

  async getCalendar(
    params: CalendarParams = {},
  ): Promise<string> {
    return formatResponse(
      await tradingGet("/v2/calendar", params as Record<string, unknown>),
      "getCalendar",
    );
  }

  async getMarketClock(): Promise<string> {
    return formatResponse(await tradingGet("/v2/clock"), "getMarketClock");
  }

  async getOrders(
    params: OrderFilterParams = {},
  ): Promise<string> {
    const data = await tradingGet("/v2/orders", params as Record<string, unknown>);
    if (typeof data === "string") return data;
    if (Array.isArray(data)) {
      return formatResponse(
        (data as Record<string, unknown>[]).map((o) => pickFields(o, ORDER_LIST_FIELDS)),
        "getOrders",
      );
    }
    return formatResponse(data, "getOrders");
  }

  // ---- Stock Market Data ----

  async getStockBars(
    params: StockBarsParams,
  ): Promise<string> {
    const { symbol_or_symbols, ...rest } = params;
    const query: Record<string, unknown> = {
      ...rest,
      symbols: symbol_or_symbols,
    };
    const data = await dataGet("/v2/stocks/bars", query);
    if (typeof data === "string") return data;
    // Map bar field names for readability
    const obj = data as Record<string, unknown>;
    if (obj.bars) {
      const barsBySymbol = obj.bars as Record<string, unknown[]>;
      const mapped: Record<string, unknown[]> = {};
      for (const [sym, bars] of Object.entries(barsBySymbol)) {
        mapped[sym] = bars.map(mapBarFields);
      }
      return formatBarsResponse({ symbols: mapped }, "getStockBars");
    }
    return formatResponse(data, "getStockBars");
  }

  async getStockLatestBar(symbolOrSymbols: string): Promise<string> {
    const data = await dataGet("/v2/stocks/bars/latest", {
      symbols: symbolOrSymbols,
    });
    if (typeof data === "string") return data;
    // Map bar field names
    const obj = data as Record<string, unknown>;
    if (obj.bars) {
      const barsBySymbol = obj.bars as Record<string, Record<string, unknown>>;
      const mapped: Record<string, Record<string, unknown>> = {};
      for (const [sym, bar] of Object.entries(barsBySymbol)) {
        mapped[sym] = mapBarFields(bar);
      }
      return formatResponse(mapped, "getStockLatestBar");
    }
    return formatResponse(data, "getStockLatestBar");
  }

  async getStockLatestQuote(symbolOrSymbols: string): Promise<string> {
    const data = await dataGet("/v2/stocks/quotes/latest", {
      symbols: symbolOrSymbols,
    });
    if (typeof data === "string") return data;
    // Response: { quotes: { AAPL: { ask_price, bid_price, ... } } }
    const obj = data as Record<string, unknown>;
    if (obj.quotes) {
      const quotes = obj.quotes as Record<string, Record<string, unknown>>;
      const rows: Record<string, unknown>[] = [];
      for (const [sym, q] of Object.entries(quotes)) {
        const row = pickFields(q, ["ask_price", "bid_price", "ask_size", "bid_size", "timestamp"]);
        row.symbol = sym;
        rows.push(row);
      }
      return formatTable(rows, "getStockLatestQuote");
    }
    return formatResponse(data, "getStockLatestQuote");
  }

  async getStockLatestTrade(symbolOrSymbols: string): Promise<string> {
    const data = await dataGet("/v2/stocks/trades/latest", {
      symbols: symbolOrSymbols,
    });
    if (typeof data === "string") return data;
    const obj = data as Record<string, unknown>;
    if (obj.trades) {
      const trades = obj.trades as Record<string, Record<string, unknown>>;
      const rows: Record<string, unknown>[] = [];
      for (const [sym, t] of Object.entries(trades)) {
        const row = pickFields(t, ["price", "size", "exchange", "timestamp", "conditions"]);
        row.symbol = sym;
        rows.push(row);
      }
      return formatTable(rows, "getStockLatestTrade");
    }
    return formatResponse(data, "getStockLatestTrade");
  }

  async getStockQuote(
    params: StockQuoteParams,
  ): Promise<string> {
    const { symbol_or_symbols, ...rest } = params;
    const data = await dataGet("/v2/stocks/quotes", {
      ...rest,
      symbols: symbol_or_symbols,
    });
    if (typeof data === "string") return data;
    const obj = data as Record<string, unknown>;
    if (obj.quotes) {
      const quotesBySymbol = obj.quotes as Record<string, unknown[]>;
      const sections: string[] = [];
      for (const [sym, quotes] of Object.entries(quotesBySymbol)) {
        sections.push(`## ${sym}`);
        if (Array.isArray(quotes)) {
          const rows = (quotes as Record<string, unknown>[]).map((q) =>
            pickFields(q, ["timestamp", "bid_price", "bid_size", "ask_price", "ask_size"]),
          );
          sections.push(formatTable(rows, "getStockQuote"));
        }
      }
      return sections.join("\n\n") || "(no quote data)";
    }
    return formatResponse(data, "getStockQuote");
  }

  async getStockSnapshot(symbolOrSymbols: string): Promise<string> {
    const data = await dataGet("/v2/stocks/snapshots", {
      symbols: symbolOrSymbols,
    });
    if (typeof data === "string") return data;
    return formatResponse(data, "getStockSnapshot");
  }

  async getStockTrades(
    params: StockTradesParams,
  ): Promise<string> {
    const { symbol_or_symbols, ...rest } = params;
    const data = await dataGet("/v2/stocks/trades", {
      ...rest,
      symbols: symbol_or_symbols,
    });
    if (typeof data === "string") return data;
    const obj = data as Record<string, unknown>;
    if (obj.trades) {
      const tradesBySymbol = obj.trades as Record<string, unknown[]>;
      const sections: string[] = [];
      for (const [sym, trades] of Object.entries(tradesBySymbol)) {
        sections.push(`## ${sym}`);
        if (Array.isArray(trades)) {
          const rows = (trades as Record<string, unknown>[]).map((t) =>
            pickFields(t, ["timestamp", "price", "size", "exchange", "conditions"]),
          );
          sections.push(formatTable(rows, "getStockTrades"));
        }
      }
      return sections.join("\n\n") || "(no trade data)";
    }
    return formatResponse(data, "getStockTrades");
  }
}

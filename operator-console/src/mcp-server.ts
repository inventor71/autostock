#!/usr/bin/env bun
// F4 Unit B — autostock steering MCP server (stdio). opencode connects to it and
// AUTO-GATES each tool via its permission system (session/tools.ts:135 calls
// ctx.ask({permission: "<server>:<tool>"}) before every MCP tool) — so the human
// confirm is enforced by opencode CORE, not by our code (this is why MCP is more
// robust than the plugin self-ask we kept breaking). Configure in opencode.json:
//   "mcp": { "autostock": { "type": "local",
//            "command": ["bun","run","<abs>/operator-console/src/mcp-server.ts"],
//            "environment": { "STEERING_DIR": "...", "STEERING_OPERATOR_TOKEN": "..." } } },
//   "permission": { "autostock_steer": "ask", "autostock_steer_read": "allow",
//     "autostock_place_stock_order": "ask", "autostock_cancel_order_by_id": "ask",
//     "autostock_cancel_all_orders": "ask", "autostock_replace_order_by_id": "ask",
//     "autostock_close_position": "ask", "autostock_close_all_positions": "ask" }
// The deterministic parse + token + file-drop write live in src/steer-handler (tested);
// the daemon RiskManager gate is the final safety regardless.
//
// F9: `steer` remains the deterministic slash-shorthand path; the tools below are the
// structured Alpaca-shaped surface (names mirror Alpaca MCP 1:1, Q6=A). Both file-drop
// a SteeringCommand the daemon runs through RiskManager→Broker.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { FileDrop } from "./filedrop";
import { handleSteer, handleSteerRead, handleStructured } from "./steer-handler";

const fd = new FileDrop(process.env.STEERING_DIR ?? "./steering");
const server = new McpServer({ name: "autostock", version: "0.0.0" });
const txt = (s: string) => ({ content: [{ type: "text" as const, text: s }] });

server.registerTool(
  "steer",
  {
    description:
      "Steer the autostock trading daemon (MUTATING). Pass the operator command VERBATIM. " +
      "opencode asks the human to confirm before this runs — you only propose, you cannot " +
      "place an order yourself. Command grammar:\n" +
      "TRADES: /buy SYM N$|Nsh · /sell SYM N%|Nsh|N$ · /flatten SYM · /flatten all · /stop SYM PRICE\n" +
      "LIFECYCLE: /pause · /resume · /halt-entries · /allow-entries · /kill\n" +
      "AGENT APPROVALS (items in snapshot.pending): /approve ID · /reject ID\n" +
      "CANCEL — two distinct meanings, pick by argument:\n" +
      "  • /cancel SYM  → cancel that symbol's resting protective orders\n" +
      "  • /cancel ID   → remove a DEFERRED/QUEUED off-hours trade. ID is from " +
      "snapshot.queued_trades; a short id-prefix (the 8 chars shown in the sidebar) works. " +
      "Use THIS (not /reject) to delete a queued trade.\n" +
      "OTHER: /unlock SYM · /note TEXT · /directive TEXT · /directive-clear ID · /answer ID TEXT",
    inputSchema: { command: z.string().describe("operator command, verbatim, e.g. /sell AAPL 50% or /cancel <id>") },
  },
  async ({ command }) => ({ content: [{ type: "text", text: handleSteer(command, fd) }] }),
);

server.registerTool(
  "steer_read",
  {
    description:
      "Read the autostock daemon state (read-only, no order authority).\n" +
      "SNAPSHOT verbs: /status · /positions · /orders · /book · /agent-trace · /why — return the live " +
      "snapshot (run_state, account [equity/cash/open_pnl], round_trip [today win_rate/realized_pnl], " +
      "positions, open_orders, pending, queued_trades, locked_symbols, market_open).\n" +
      "MONITOR verbs (deep view, from monitor.json): /turns (turn cost/activity) · /decisions (recent " +
      "decisions) · /log (agent log tail).",
    inputSchema: { command: z.string().describe("a read command, e.g. /status or /turns") },
  },
  async ({ command }) => ({ content: [{ type: "text", text: handleSteerRead(command, fd) }] }),
);

// ---- F9 structured Alpaca-shaped order tools (MUTATING, opencode `ask`-gated) ---- #
// F21: cross-field structural validation runs SYNCHRONOUSLY (L1 zod .refine()) so
// the agent sees errors in the tool response and can retry, following the Alpaca MCP
// pattern. L2 (degenerate-value check) runs in handleStructured before the file-drop
// write. L3 (daemon) does price-based sizing + defense-in-depth.

// -- place_stock_order ----------------------------------------------------------- #

const placeOrderShape = {
  symbol: z.string().min(1).describe("ticker symbol (e.g. AAPL)"),
  side: z.enum(["buy", "sell"]),
  qty: z.number().positive().optional()
    .describe("share count (whole shares preferred); do NOT set if using notional"),
  notional: z.number().positive().optional()
    .describe("$ amount; market+day only. Omit if using qty. Do NOT pass 0 or placeholder"),
  order_type: z.enum(["market", "limit", "stop", "stop_limit", "trailing_stop"]).default("market"),
  time_in_force: z.enum(["day", "gtc", "ioc", "fok", "opg", "cls"]).default("day"),
  limit_price: z.number().positive().optional()
    .describe("omit if unused; do NOT pass 0 or placeholder"),
  stop_price: z.number().positive().optional()
    .describe("omit if unused; do NOT pass 0 or placeholder"),
  trail_price: z.number().positive().optional()
    .describe("only for trailing_stop order_type; omit otherwise"),
  trail_percent: z.number().positive().lt(100).optional()
    .describe("only for trailing_stop order_type; omit otherwise. Must be < 100"),
  extended_hours: z.boolean().default(false).optional(),
  client_order_id: z.string().optional(),
  order_class: z.enum(["simple", "bracket", "oco", "oto"]).default("simple"),
  take_profit: z.number().positive().optional()
    .describe("omit if unused; do NOT pass 0 or placeholder"),
  stop_loss: z.number().positive().optional()
    .describe("omit if unused; do NOT pass 0 or placeholder"),
  force: z.boolean().optional(),
};

const placeOrderValidator = z.object(placeOrderShape)
  .refine(d => !(d.qty != null && d.notional != null), {
    message: "specify either qty or notional, not both",
    path: ["qty"],
  })
  .refine(d => d.qty != null || d.notional != null, {
    message: "qty or notional required",
  })
  .refine(d => d.notional == null || (d.order_type === "market" && d.time_in_force === "day"), {
    message: "notional is only allowed for market + day orders",
    path: ["notional"],
  })
  .refine(d => d.order_type === "trailing_stop" || (d.trail_price == null && d.trail_percent == null), {
    message: "trail_price/trail_percent only valid with order_type=trailing_stop",
    path: ["trail_price"],
  })
  .refine(d => d.order_type !== "trailing_stop" || d.trail_price != null || d.trail_percent != null, {
    message: "trailing_stop requires trail_price or trail_percent",
    path: ["trail_price"],
  })
  .refine(d => d.time_in_force !== "opg" && d.time_in_force !== "cls", {
    message: "opg/cls TIF is not yet supported",
    path: ["time_in_force"],
  })
  .refine(d => d.order_class !== "oto", {
    message: "oto order_class is not yet supported",
    path: ["order_class"],
  });

server.registerTool(
  "place_stock_order",
  {
    description:
      "Place a stock order through the gated daemon (MUTATING; opencode asks the human to " +
      "confirm). RiskManager validates/clamps size, auto-attaches protection, and may reject " +
      "with a suggestion — you propose, you cannot place autonomously.\n\n" +
      "Omit optional fields entirely if unused. Never pass 0, 0.01, or placeholder values. " +
      "Errors are returned synchronously — read the error and retry with corrected args.\n\n" +
      "Use `notional` only for market+day; otherwise an integer `qty`. Set `force: true` to " +
      "override budget/pool/breaker limits (price-sanity and auto-protection are NOT overridable). " +
      "opg/cls TIF and oto class are not yet supported (rejected).",
    inputSchema: placeOrderShape,
  },
  async (args) => {
    const parsed = placeOrderValidator.safeParse(args);
    if (!parsed.success) {
      const msg = parsed.error.issues.map(i => i.message).join("; ");
      return txt(`rejected: ${msg}`);
    }
    return txt(handleStructured("place_order", parsed.data, fd));
  },
);

server.registerTool(
  "cancel_order_by_id",
  {
    description: "Cancel a specific resting broker order by its id (MUTATING, confirm).",
    inputSchema: { order_id: z.string().min(1) },
  },
  async ({ order_id }) => txt(handleStructured("cancel_order", { order_id }, fd)),
);

server.registerTool(
  "cancel_all_orders",
  {
    description: "Cancel all resting orders, or all for one symbol (MUTATING, confirm).",
    inputSchema: { symbol: z.string().optional() },
  },
  async ({ symbol }) => txt(handleStructured("cancel_all", { symbol }, fd)),
);

server.registerTool(
  "replace_order_by_id",
  {
    description:
      "Modify a resting SIMPLE order in place (qty/limit/stop/trail/TIF). Bracket/OCO legs " +
      "cannot be replaced — cancel and re-place instead (MUTATING, confirm).",
    inputSchema: {
      order_id: z.string(),
      qty: z.number().int().positive().optional(),
      limit_price: z.number().positive().optional(),
      stop_price: z.number().positive().optional(),
      trail: z.number().positive().optional(),
      time_in_force: z.enum(["day", "gtc", "ioc", "fok"]).optional(),
    },
  },
  async ({ order_id, qty, limit_price, stop_price, trail, time_in_force }) =>
    txt(handleStructured("replace_order",
      { order_id, qty, limit_price, stop_price, trail, time_in_force }, fd)),
);

// -- close_position ------------------------------------------------------------- #
// F21: qty/percentage removed — the daemon always does a full-position flatten
// via _flatten_symbol(); partial close is not yet implemented.  These fields may
// be re-added when partial-close support lands.

server.registerTool(
  "close_position",
  {
    description:
      "Close (flatten) the ENTIRE position for a symbol (MUTATING, confirm). " +
      "Partial close is not yet supported — this always closes 100% of the position.",
    inputSchema: {
      symbol: z.string().min(1).describe("ticker symbol (e.g. AAPL)"),
    },
  },
  async ({ symbol }) => txt(handleStructured("close_position", { symbol }, fd)),
);

server.registerTool(
  "close_all_positions",
  {
    description:
      "Close every open position (MUTATING, confirm). " +
      "Set cancel_orders: true to cancel resting orders before closing; omit otherwise.",
    inputSchema: { cancel_orders: z.boolean().optional() },
  },
  async ({ cancel_orders }) => txt(handleStructured("close_all", { cancel_orders }, fd)),
);

await server.connect(new StdioServerTransport());

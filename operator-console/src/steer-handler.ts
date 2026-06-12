// F4 Unit B — steer command handlers (deterministic), reused by the MCP server.
//
// CONFIRM is opencode's MCP auto-gate (permission:{"autostock_steer":"ask"}), enforced by
// opencode CORE before the tool runs — NOT by this code (session/tools.ts:135). That removes
// the failure mode where our own ctx.ask gate could be mis-keyed or removed. So reaching
// handleSteer means the human already approved. These are pure parse+(read|write) fns.

import { readFileSync } from "node:fs";
import { FileDrop } from "./filedrop";
import { ParseError, parseCommand } from "./parser";
import type { SteeringVerb } from "./schema";

// F28: static UI legend — TUI element meanings, served via `/ui-legend [element]`.
// Read from the JSON next to this module (NOT a top-level `import`: a malformed file
// must degrade gracefully here, not crash the MCP server at spawn). The daemon and the
// $STEERING_DIR are uninvolved — this is a static, repo-committed dictionary.
interface UiLegendEntry { id: string; meaning: string; location?: string }

function loadUiLegend(): UiLegendEntry[] {
  try {
    const raw = readFileSync(new URL("./ui-legend.json", import.meta.url), "utf8");
    const parsed = JSON.parse(raw) as { entries?: UiLegendEntry[] };
    return Array.isArray(parsed.entries) ? parsed.entries : [];
  } catch {
    return [];
  }
}

/** Serve the `/ui-legend [element]` read verb. `raw` is the full command line
 *  (e.g. "ui-legend topbar.today_cost"); the element token, if any, is the word
 *  after the verb (READ_VERBS pass `args.raw` only — no parser-side split). */
export function handleUiLegend(raw: string): string {
  const entries = loadUiLegend();
  if (entries.length === 0) return "(ui legend unavailable)";
  const element = raw.trim().split(/\s+/)[1]; // [0] = "ui-legend"
  if (element) {
    const hit = entries.find((e) => e.id === element);
    if (!hit) return JSON.stringify({ legend: [], error: `element '${element}' not found` });
    return JSON.stringify({ legend: [hit] });
  }
  return JSON.stringify({ legend: entries });
}

// ---- F21 L2 degenerate-value helpers ------------------------------------------- //
// These run SYNCHRONOUSLY before the file-drop write so the agent sees the rejection
// in the tool response and can retry (Alpaca MCP pattern).  L1 (zod .refine()) catches
// cross-field violations; L2 catches single-field junk like 0.01 placeholders that
// .positive() passes. L3 (daemon) does price-based sizing + defense-in-depth.

const DEGENERATE_THRESHOLD = 0.01; // ≤ this for a positive number = placeholder

/** True when a positive number is ≤ DEGENERATE_THRESHOLD — a likely placeholder. */
export function isDegenerate(v: unknown): boolean {
  return typeof v === "number" && v > 0 && v <= DEGENERATE_THRESHOLD;
}

const PLACE_DEGENERATE_FIELDS = [
  "qty", "notional", "limit_price", "stop_price", "trail_price", "trail_percent",
  "take_profit", "stop_loss",
] as const;

/** Validate place_order args for degenerate field values. Returns error string or null. */
export function validatePlaceOrderArgs(args: Record<string, unknown>): string | null {
  for (const f of PLACE_DEGENERATE_FIELDS) {
    if (isDegenerate(args[f])) {
      return `rejected: ${f} ${args[f]} looks like a placeholder; omit if unused`;
    }
  }
  return null;
}

/** Validate replace_order args for degenerate field values. Returns error string or null. */
export function validateReplaceOrderArgs(args: Record<string, unknown>): string | null {
  for (const f of ["qty", "limit_price", "stop_price", "trail"]) {
    if (isDegenerate(args[f])) {
      return `rejected: ${f} ${args[f]} looks like a placeholder; omit if unused`;
    }
  }
  return null;
}

/** Mutating path (buy/sell/short/cover/flatten/stop/lifecycle/approval/...). Auto-gated by opencode. */
export function handleSteer(command: string, fd: FileDrop): string {
  let draft;
  try {
    draft = parseCommand(command);
  } catch (e) {
    return `rejected: ${e instanceof ParseError ? e.message : String(e)}`;
  }
  if (draft.readOnly) return "this is a read command — use the steer_read tool instead";
  if (!fd.hasToken()) {
    return "rejected: operator token missing (STEERING_OPERATOR_TOKEN); write disabled";
  }
  const id = fd.send(draft.verb, draft.args);
  return `OK ${draft.verb} ${id} — ${draft.echo}`;
}

/** F9: structured Alpaca-shaped order/management path. The MCP tool's zod schema
 * already validated `args` at the boundary (SECURITY-13); here we strip undefined
 * keys (so the daemon's PlaceOrderArgs extra="forbid" sees only provided fields,
 * NFR-3), run L2 degenerate-value checks (F21), and file-drop the command.
 * Auto-gated by opencode's permission `ask` (FR-4) exactly like `steer`; the
 * daemon RiskManager is the final safety. The token is attached in FileDrop and
 * never returned (SECURITY-03). */
export function handleStructured(
  verb: SteeringVerb,
  args: Record<string, unknown>,
  fd: FileDrop,
): string {
  if (!fd.hasToken()) {
    return "rejected: operator token missing (STEERING_OPERATOR_TOKEN); write disabled";
  }
  // F21 L2: degenerate-value check (synchronous, before file-drop)
  if (verb === "place_order") {
    const err = validatePlaceOrderArgs(args);
    if (err) return err;
  } else if (verb === "replace_order") {
    const err = validateReplaceOrderArgs(args);
    if (err) return err;
  }
  const clean: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(args)) if (v !== undefined) clean[k] = v;
  const id = fd.send(verb, clean);
  return `OK ${verb} ${id}`;
}

// F6: deep-monitoring views are served from steering/monitor.json, not the snapshot.
// `log` returns just the log tail; turns/decisions return their slice.
const MONITOR_VERBS: Record<string, string> = { turns: "turns", decisions: "decisions", log: "log" };

/** Read-only path (status/positions/orders/...). No order authority; not gated.
 *  `supervisor` (F39) gates the codebase-introspection verb: only supervisor-launched
 *  consoles may read the project tree; normal mode gets a generic refusal that does NOT
 *  mention supervisor mode (FR-4/Q4). Defaults false so any non-supervisor caller is denied
 *  (fail-closed, SECURITY-15). mcp-server passes process.env.AUTOSTOCK_SUPERVISOR === "on". */
export function handleSteerRead(command: string, fd: FileDrop, supervisor = false): string {
  let draft;
  try {
    draft = parseCommand(command);
  } catch (e) {
    return `rejected: ${e instanceof ParseError ? e.message : String(e)}`;
  }
  if (!draft.readOnly) {
    return "this is a mutating command — use the steer tool (opencode will ask you to confirm)";
  }
  // F29: codebase tree lives in its own file (generated once at daemon startup,
  // not periodically refreshed like monitor/snapshot).
  // F39: codebase introspection is supervisor-only. Normal mode refuses generically
  // (no mention of supervisor mode — it stays a developer-only capability).
  if (draft.verb === "codebase") {
    if (!supervisor) return "codebase introspection is not available in this console.";
    const cb = fd.readCodebase();
    if (!cb) return "(no codebase tree yet — daemon may not have published it)";
    return `codebase tree:\n${cb.tree ?? JSON.stringify(cb)}`;
  }
  // F28: static UI legend (TUI element meanings). Served from a repo-committed JSON,
  // not the daemon — `draft.args.raw` carries the full line incl. an optional element.
  if (draft.verb === "ui-legend") {
    return handleUiLegend(String(draft.args.raw ?? ""));
  }
  // F53: position thesis read — agent's thesis/plan/call-vs-outcome for a symbol.
  // `/thesis AAPL` reads workspace/positions/AAPL.md; `/theses` lists all symbols.
  if (draft.verb === "thesis") {
    const symbol = String(draft.args.raw ?? "").trim().split(/\s+/)[1];
    if (!symbol) return "(thesis: symbol required, e.g. /thesis AAPL)";
    const content = fd.readThesis(symbol);
    if (content === null) return `(no thesis file found for ${symbol.toUpperCase()})`;
    return `thesis ${symbol.toUpperCase()}:\n${content}`;
  }
  if (draft.verb === "theses") {
    const symbols = fd.listTheses();
    if (symbols.length === 0) return "(no thesis files found in workspace/positions/)";
    return `theses: ${symbols.join(", ")}`;
  }
  // F72: research-turn screening funnel — the agent's per-candidate verdicts
  // (entered/watchlist/passed + reason) joined with the auto-saved scoreboard
  // quant snapshot. `/screening` → latest day; `/screening 2026-06-10` → that day.
  if (draft.verb === "screening") {
    const arg = String(draft.args.raw ?? "").trim().split(/\s+/)[1];
    // SECURITY-05: strict date allowlist BEFORE the value goes anywhere near a path.
    if (arg !== undefined && !/^\d{4}-\d{2}-\d{2}$/.test(arg)) {
      return "(screening: invalid date, expected YYYY-MM-DD)";
    }
    const date = arg ?? fd.latestScreeningDate();
    if (!date) return "(no screening data yet)";
    const data = fd.readScreening(date);
    if (!data) return `(no screening data for ${date})`;
    return formatScreening(date, data);
  }
  // F6: dispatch deep-monitoring verbs to monitor.json (previously every read verb,
  // even `log`, fell through to the snapshot — critic #3).
  const key = MONITOR_VERBS[draft.verb];
  if (key) {
    const mon = fd.readMonitor();
    if (!mon) return "(no monitor data yet)";
    return `${key}: ${JSON.stringify(mon[key] ?? null)}`;
  }
  const snap = fd.readSnapshot();
  return snap ? `snapshot: ${JSON.stringify(snap)}` : "(no snapshot yet)";
}

// ---- F72: /screening rendering -------------------------------------------- #

/** "+0.3" / "-2.3" / "?" — signed change for the compact scan rows. */
function signed(v: unknown): string {
  return typeof v === "number" ? (v >= 0 ? `+${v}` : `${v}`) : "?";
}

/** "09:40" from an ISO timestamp, or the raw value when it isn't one. */
function hhmm(ts: unknown): string {
  const s = String(ts ?? "?");
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s) ? s.slice(11, 16) : s;
}

function formatScreening(
  date: string,
  data: { scan: Record<string, unknown> | null; scanUnreadable: boolean; verdicts: Array<Record<string, unknown>> },
): string {
  const scan = data.scan as { ts?: unknown; count?: unknown; rows?: unknown } | null;
  const rows = Array.isArray(scan?.rows) ? (scan.rows as Array<Record<string, unknown>>) : [];
  const lines: string[] = [];
  lines.push(
    scan
      ? `screening ${date} (scan ${String(scan.ts ?? "?")}, ${String(scan.count ?? rows.length)} symbols):`
      : `screening ${date}:`,
  );
  if (data.verdicts.length === 0) {
    lines.push("verdicts: (none recorded)");
  } else {
    lines.push(`verdicts (${data.verdicts.length}):`);
    for (const v of data.verdicts) {
      lines.push(`  ${hhmm(v.ts)} ${String(v.symbol ?? "?")} ${String(v.verdict ?? "?")} — ${String(v.reason ?? "")}`);
    }
  }
  if (data.scanUnreadable) {
    lines.push("scan: (unreadable)");
  } else if (!scan) {
    lines.push("scan: (none)");
  } else {
    lines.push("scan (symbol close chg1d% chg5d% chg20d% rsi volx dist20d%):");
    for (const r of rows) {
      if (r.error !== undefined) {
        lines.push(`  ${String(r.symbol ?? "?")} error: ${String(r.error)}`);
      } else {
        lines.push(
          `  ${String(r.symbol ?? "?")} ${String(r.close ?? "?")} ${signed(r.chg_1d)} ${signed(r.chg_5d)} ` +
          `${signed(r.chg_20d)} ${String(r.rsi_14 ?? "?")} ${String(r.vol_ratio ?? "?")}x ${signed(r.dist_high_20d_pct)}`,
        );
      }
    }
  }
  return lines.join("\n");
}

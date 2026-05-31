// F4 Unit B — steer command handlers (deterministic), reused by the MCP server.
//
// CONFIRM is opencode's MCP auto-gate (permission:{"autostock_steer":"ask"}), enforced by
// opencode CORE before the tool runs — NOT by this code (session/tools.ts:135). That removes
// the failure mode where our own ctx.ask gate could be mis-keyed or removed. So reaching
// handleSteer means the human already approved. These are pure parse+(read|write) fns.

import { FileDrop } from "./filedrop";
import { ParseError, parseCommand } from "./parser";
import type { SteeringVerb } from "./schema";

/** Mutating path (buy/sell/flatten/stop/lifecycle/approval/...). Auto-gated by opencode. */
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
 * NFR-3) and file-drop the command. Auto-gated by opencode's permission `ask`
 * (FR-4) exactly like `steer`; the daemon RiskManager is the final safety. The
 * token is attached in FileDrop and never returned (SECURITY-03). */
export function handleStructured(
  verb: SteeringVerb,
  args: Record<string, unknown>,
  fd: FileDrop,
): string {
  if (!fd.hasToken()) {
    return "rejected: operator token missing (STEERING_OPERATOR_TOKEN); write disabled";
  }
  const clean: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(args)) if (v !== undefined) clean[k] = v;
  const id = fd.send(verb, clean);
  return `OK ${verb} ${id}`;
}

// F6: deep-monitoring views are served from steering/monitor.json, not the snapshot.
// `log` returns just the log tail; turns/decisions return their slice.
const MONITOR_VERBS: Record<string, string> = { turns: "turns", decisions: "decisions", log: "log" };

/** Read-only path (status/positions/orders/...). No order authority; not gated. */
export function handleSteerRead(command: string, fd: FileDrop): string {
  let draft;
  try {
    draft = parseCommand(command);
  } catch (e) {
    return `rejected: ${e instanceof ParseError ? e.message : String(e)}`;
  }
  if (!draft.readOnly) {
    return "this is a mutating command — use the steer tool (opencode will ask you to confirm)";
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

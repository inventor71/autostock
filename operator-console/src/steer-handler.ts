// F4 Unit B — steer command handlers (deterministic), reused by the MCP server.
//
// CONFIRM is opencode's MCP auto-gate (permission:{"autostock_steer":"ask"}), enforced by
// opencode CORE before the tool runs — NOT by this code (session/tools.ts:135). That removes
// the failure mode where our own ctx.ask gate could be mis-keyed or removed. So reaching
// handleSteer means the human already approved. These are pure parse+(read|write) fns.

import { FileDrop } from "./filedrop";
import { ParseError, parseCommand } from "./parser";

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
  const snap = fd.readSnapshot();
  return snap ? `snapshot: ${JSON.stringify(snap)}` : "(no snapshot yet)";
}

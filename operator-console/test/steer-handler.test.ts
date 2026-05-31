import { afterEach, beforeEach, expect, test } from "bun:test";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { FileDrop } from "../src/filedrop";
import { handleSteer, handleSteerRead, handleStructured } from "../src/steer-handler";

// The MCP server's tool logic. Confirm is opencode's MCP auto-gate (verified live via
// bun dev); these cover the deterministic parse+(read|write) the handlers own.
let dir: string;
let fd: FileDrop;
beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "mcp-"));
  fd = new FileDrop(dir, "tok");
});
afterEach(() => rmSync(dir, { recursive: true, force: true }));

function verbs(): string[] {
  try {
    return readFileSync(fd.commandsFile, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l).verb);
  } catch {
    return [];
  }
}

test("handleSteer: mutating command writes confirmed+token", () => {
  expect(handleSteer("/sell AAPL 50%", fd)).toContain("OK sell");
  expect(verbs()).toEqual(["sell"]);
});

test("handleSteer: read verb routed to steer_read, no write", () => {
  expect(handleSteer("/status", fd)).toContain("steer_read");
  expect(verbs()).toEqual([]);
});

test("handleSteer: malformed rejected, no write", () => {
  expect(handleSteer("/buy AAPL 1000", fd)).toContain("rejected");
  expect(verbs()).toEqual([]);
});

test("handleSteer: no token -> write disabled", () => {
  const fd2 = new FileDrop(dir, "");
  expect(handleSteer("/pause", fd2)).toContain("token missing");
  expect(verbs()).toEqual([]);
});

test("handleSteerRead: returns snapshot, never writes", () => {
  writeFileSync(fd.snapshotFile, JSON.stringify({ run_state: { paused: false }, positions: {} }));
  expect(handleSteerRead("/status", fd)).toContain("snapshot");
  expect(verbs()).toEqual([]);
});

test("handleSteerRead: mutating command routed to steer (with confirm), no write", () => {
  expect(handleSteerRead("/sell AAPL 50%", fd)).toContain("use the steer tool");
  expect(verbs()).toEqual([]);
});

// F6: deep-monitoring verbs read monitor.json, not the snapshot.
test("handleSteerRead: /turns returns the turns slice from monitor.json", () => {
  writeFileSync(fd.monitorFile, JSON.stringify({ turns: { today_count: 3 }, decisions: [], log: [] }));
  const out = handleSteerRead("/turns", fd);
  expect(out).toContain("turns:");
  expect(out).toContain("today_count");
});

test("handleSteerRead: /decisions and /log dispatch to their slices", () => {
  writeFileSync(fd.monitorFile, JSON.stringify({ turns: {}, decisions: ["10:00 AAPL BUY"], log: ["boot"] }));
  expect(handleSteerRead("/decisions", fd)).toContain("AAPL BUY");
  expect(handleSteerRead("/log", fd)).toContain("boot");
});

test("handleSteerRead: monitor verb with no monitor.json is graceful", () => {
  expect(handleSteerRead("/turns", fd)).toContain("no monitor data");
  expect(verbs()).toEqual([]);
});

test("handleSteerRead: /status still returns snapshot (not monitor)", () => {
  writeFileSync(fd.snapshotFile, JSON.stringify({ account: { equity: 1 } }));
  writeFileSync(fd.monitorFile, JSON.stringify({ turns: { today_count: 9 } }));
  expect(handleSteerRead("/status", fd)).toContain("snapshot");
});

// ---- F9 structured order path -------------------------------------------- #
function records(): Array<{ verb: string; args: Record<string, unknown>; token: string }> {
  try {
    return readFileSync(fd.commandsFile, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l));
  } catch {
    return [];
  }
}

test("handleStructured: place_order drops undefined keys, attaches token, never echoes it", () => {
  const out = handleStructured("place_order",
    { symbol: "AAPL", side: "buy", qty: 10, notional: undefined, order_type: "market" }, fd);
  expect(out).toContain("OK place_order");
  expect(out).not.toContain("tok"); // token never in the tool result (SECURITY-03)
  const recs = records();
  expect(recs).toHaveLength(1);
  expect(recs[0].verb).toBe("place_order");
  expect(recs[0].token).toBe("tok");
  expect(recs[0].args).toEqual({ symbol: "AAPL", side: "buy", qty: 10, order_type: "market" }); // no `notional`
  expect("notional" in recs[0].args).toBe(false);
});

test("handleStructured: no token -> write disabled, no file drop", () => {
  const fd2 = new FileDrop(dir, "");
  expect(handleStructured("close_all", { cancel_orders: true }, fd2)).toContain("token missing");
  expect(records()).toEqual([]);
});

test("handleStructured: replace_order forwards only provided change keys", () => {
  handleStructured("replace_order",
    { order_id: "o1", qty: 5, limit_price: undefined, stop_price: undefined, trail: undefined, time_in_force: undefined }, fd);
  const r = records()[0];
  expect(r.verb).toBe("replace_order");
  expect(r.args).toEqual({ order_id: "o1", qty: 5 });
});

// ---- F21 L2 degenerate check in handleStructured ----------------------------- #

test("handleStructured: place_order rejects degenerate take_profit before file-drop", () => {
  const out = handleStructured("place_order",
    { symbol: "AAPL", side: "buy", qty: 10, take_profit: 0.01 }, fd);
  expect(out).toContain("rejected");
  expect(out).toContain("take_profit 0.01 looks like a placeholder");
  expect(records()).toEqual([]); // nothing written
});

test("handleStructured: replace_order rejects degenerate limit_price before file-drop", () => {
  const out = handleStructured("replace_order",
    { order_id: "abc", limit_price: 0.01 }, fd);
  expect(out).toContain("rejected");
  expect(out).toContain("limit_price 0.01 looks like a placeholder");
  expect(records()).toEqual([]);
});

test("handleStructured: close_position with symbol only writes (qty/percentage removed, critic fix)", () => {
  const out = handleStructured("close_position",
    { symbol: "AAPL" }, fd);
  expect(out).toContain("OK close_position");
  expect(records()).toHaveLength(1);
});

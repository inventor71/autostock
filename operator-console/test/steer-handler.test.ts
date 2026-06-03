import { afterEach, beforeEach, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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
afterEach(() => {
  // Clean up the shared workspace/positions directory (derived from steeringDir
  // as join(steeringDir, "..", "workspace", "positions") which is shared when
  // steeringDir is a temp path).
  try { rmSync(join(dir, "..", "workspace"), { recursive: true, force: true }); } catch {}
  rmSync(dir, { recursive: true, force: true });
});

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

// ---- F28 UI legend -------------------------------------------------------- #
test("handleSteerRead: /ui-legend returns the full legend, never writes", () => {
  const out = handleSteerRead("/ui-legend", fd);
  const parsed = JSON.parse(out);
  expect(Array.isArray(parsed.legend)).toBe(true);
  expect(parsed.legend.length).toBeGreaterThan(0);
  expect(parsed.legend.some((e: { id: string }) => e.id === "topbar.today_cost")).toBe(true);
  expect(verbs()).toEqual([]);
});

test("handleSteerRead: /ui-legend <element> returns just that entry with its meaning", () => {
  const out = handleSteerRead("/ui-legend topbar.today_cost", fd);
  const parsed = JSON.parse(out);
  expect(parsed.legend).toHaveLength(1);
  expect(parsed.legend[0].id).toBe("topbar.today_cost");
  expect(parsed.legend[0].meaning).toContain("비용");
});

test("handleSteerRead: /ui-legend with unknown element returns a not-found error", () => {
  const out = handleSteerRead("/ui-legend does.not.exist", fd);
  const parsed = JSON.parse(out);
  expect(parsed.legend).toEqual([]);
  expect(parsed.error).toContain("not found");
});

// ---- F39 /codebase supervisor gating ------------------------------------- #
test("handleSteerRead: /codebase is refused in normal mode (default), no tree, no 'supervisor' word", () => {
  writeFileSync(join(dir, "codebase.json"), JSON.stringify({ tree: "src/\n  agent/" }));
  const out = handleSteerRead("/codebase", fd); // supervisor defaults false (fail-closed)
  expect(out).not.toContain("codebase tree:");
  expect(out).not.toContain("src/");
  expect(out.toLowerCase()).not.toContain("supervisor"); // FR-4/Q4: never reveal the mode
});

test("handleSteerRead: /codebase returns the tree in supervisor mode (F29 preserved)", () => {
  writeFileSync(join(dir, "codebase.json"), JSON.stringify({ tree: "src/\n  agent/" }));
  const out = handleSteerRead("/codebase", fd, true);
  expect(out).toContain("codebase tree:");
  expect(out).toContain("src/");
});

test("handleSteerRead: other read verbs unaffected by the supervisor flag", () => {
  // /status must still answer in normal mode (operational reads stay open, FR-6)
  expect(handleSteerRead("/status", fd, false)).toContain("snapshot");
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

// ---- F53 position thesis read -------------------------------------------- #

test("handleSteerRead: /thesis <SYMBOL> returns file content", () => {
  mkdirSync(fd.positionsDir, { recursive: true });
  writeFileSync(join(fd.positionsDir, "AAPL.md"), "# AAPL Thesis\n\nBuy thesis.", "utf8");
  const out = handleSteerRead("/thesis AAPL", fd);
  expect(out).toContain("thesis AAPL:");
  expect(out).toContain("# AAPL Thesis");
  expect(out).toContain("Buy thesis.");
});

test("handleSteerRead: /thesis with no file returns graceful message", () => {
  const out = handleSteerRead("/thesis UNKNOWN", fd);
  expect(out).toContain("no thesis file found for UNKNOWN");
});

test("handleSteerRead: /thesis with no symbol shows usage", () => {
  const out = handleSteerRead("/thesis", fd);
  expect(out).toContain("symbol required");
});

test("handleSteerRead: /theses lists symbols", () => {
  mkdirSync(fd.positionsDir, { recursive: true });
  writeFileSync(join(fd.positionsDir, "MSFT.md"), "...", "utf8");
  writeFileSync(join(fd.positionsDir, "AAPL.md"), "...", "utf8");
  const out = handleSteerRead("/theses", fd);
  expect(out).toContain("theses:");
  expect(out).toContain("AAPL, MSFT");
});

test("handleSteerRead: /theses with no files returns graceful message", () => {
  // Ensure clean state — afterEach cleans workspace/ but be defensive.
  try { rmSync(join(dir, "..", "workspace"), { recursive: true, force: true }); } catch {}
  const out = handleSteerRead("/theses", fd);
  expect(out).toContain("no thesis files found");
});

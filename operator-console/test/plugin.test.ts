import { afterEach, beforeEach, expect, test } from "bun:test";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import plugin, { SteerPlugin } from "../src/plugin";

// Verifies the opencode plugin SHAPE (default export {id, server}) + the steer tool's
// execute logic against a fake ToolContext. opencode itself can't run here; this covers
// everything except opencode invoking ctx.ask in its real UI.

let dir: string;
beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "plug-"));
  process.env.STEERING_DIR = dir;
  process.env.STEERING_OPERATOR_TOKEN = "smoke-tok";
});
afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
  delete process.env.STEERING_DIR;
  delete process.env.STEERING_OPERATOR_TOKEN;
});

function writtenVerbs(): string[] {
  try {
    return readFileSync(join(dir, "commands.jsonl"), "utf8").trim().split("\n").filter(Boolean)
      .map((l) => JSON.parse(l).verb);
  } catch {
    return [];
  }
}

async function steerTool() {
  const hooks = await SteerPlugin({} as never);
  return hooks.tool!.steer;
}

test("default export is the V1 module shape opencode requires", () => {
  expect(typeof plugin.server).toBe("function"); // {id, server} — readV1Plugin reads .server
  expect(plugin.id).toBe("autostock-steer");
});

// The tool calls ctx.ask itself (plugin tools are NOT auto-gated by opencode). ctx.ask
// resolves when the human approves (config permission:{steer:"ask"}), throws on deny.
const approve = { ask: async () => {} } as never;
const deny = { ask: async () => { throw new Error("denied"); } } as never;

test("mutating command: ctx.ask approves -> confirmed+token write", async () => {
  const steer = await steerTool();
  const res = await steer.execute({ command: "/pause" }, approve);
  expect(String(res)).toContain("OK pause");
  expect(writtenVerbs()).toEqual(["pause"]);
});

test("ctx.ask denied -> cancelled, no write (fail-closed)", async () => {
  const steer = await steerTool();
  const res = await steer.execute({ command: "/sell AAPL 50%" }, deny);
  expect(String(res)).toContain("cancelled");
  expect(writtenVerbs()).toEqual([]);
});

test("read command returns snapshot, never writes (no ask)", async () => {
  const steer = await steerTool();
  let asked = false;
  const res = await steer.execute({ command: "/status" }, { ask: async () => { asked = true; } } as never);
  expect(asked).toBe(false);
  expect(writtenVerbs()).toEqual([]);
  expect(String(res)).toMatch(/snapshot|no snapshot/);
});

test("malformed command rejected without ask/write", async () => {
  const steer = await steerTool();
  const res = await steer.execute({ command: "/buy AAPL 1000" }, approve);
  expect(String(res)).toContain("rejected");
  expect(writtenVerbs()).toEqual([]);
});

test("no token -> write disabled (before any ask)", async () => {
  delete process.env.STEERING_OPERATOR_TOKEN;
  const steer = await steerTool();
  const res = await steer.execute({ command: "/pause" }, approve);
  expect(String(res)).toContain("token missing");
  expect(writtenVerbs()).toEqual([]);
});

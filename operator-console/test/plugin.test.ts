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

// NOTE: the human confirm is opencode's TOOL-LEVEL permission (`permission:{steer:"ask"}`),
// enforced BEFORE execute runs — so reaching execute means the human already approved.
// These tests cover execute's own logic (write/read/reject/token); the live approval
// prompt is verified via `bun dev` (it auto-confirmed before because the config rule was missing).
test("mutating command writes confirmed+token (execute runs only post-approval)", async () => {
  const steer = await steerTool();
  const res = await steer.execute({ command: "/pause" }, {} as never);
  expect(String(res)).toContain("OK pause");
  expect(writtenVerbs()).toEqual(["pause"]);
});

test("read command returns snapshot, never writes", async () => {
  const steer = await steerTool();
  const res = await steer.execute({ command: "/status" }, {} as never);
  expect(writtenVerbs()).toEqual([]);
  expect(String(res)).toMatch(/snapshot|no snapshot/);
});

test("malformed command rejected without write", async () => {
  const steer = await steerTool();
  const res = await steer.execute({ command: "/buy AAPL 1000" }, {} as never);
  expect(String(res)).toContain("rejected");
  expect(writtenVerbs()).toEqual([]);
});

test("no token -> write disabled", async () => {
  delete process.env.STEERING_OPERATOR_TOKEN;
  const steer = await steerTool();
  const res = await steer.execute({ command: "/pause" }, {} as never);
  expect(String(res)).toContain("token missing");
  expect(writtenVerbs()).toEqual([]);
});

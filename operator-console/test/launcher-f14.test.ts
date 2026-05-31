// F14 launcher self-heal: when the unit is `active` but the snapshot isn't advancing,
// wait out a long patience window (busy daemons advance and are left alone), then
// auto-restart ONCE and re-wait. Mirrors the injected-dep harness in launcher.test.ts.

import { describe, expect, test } from "bun:test";
import {
  DaemonService,
  DaemonStartError,
  WEDGE_PATIENCE_MS,
  type DaemonDeps,
  type Runner,
} from "../launcher/daemon";

function makeClock() {
  let t = 1_000_000;
  return {
    now: () => t,
    get: () => t,
    sleep: async (ms: number) => {
      t += ms;
    },
  };
}

function svc(deps: DaemonDeps) {
  const cfg = {
    autostockRoot: "/srv/app",
    steeringDir: "/srv/app/steering",
    installPath: "/home/u/.local/bin/autostock",
    consoleCwd: "/srv/app/operator-console/cli",
    mcpServerPath: "/srv/app/operator-console/src/mcp-server.ts",
    token: "tok",
  };
  return new DaemonService(cfg, deps);
}

/**
 * Harness for the `active` (wedge-candidate) path.
 *  - mode "wedgedThenHealthy": snapshot is frozen until `restart`, then advances.
 *  - mode "busy":              snapshot advances from the start (no restart expected).
 *  - mode "wedgedForever":     snapshot stays frozen even after restart (fail-closed).
 *  - mode "recoverBeforeRestart": frozen during the patience wait, then fresh+advancing
 *                                  right after — exercises the pre-restart race guard.
 */
function harness(mode: "wedgedThenHealthy" | "busy" | "wedgedForever" | "recoverBeforeRestart") {
  const clk = makeClock();
  const calls: string[] = [];
  let restarted = false;
  let patienceDone = false;

  const run: Runner = async (args: string[]) => {
    calls.push(args.join(" "));
    if (args.includes("is-active")) return { code: 0, stdout: "active", stderr: "" };
    if (args.includes("is-enabled")) return { code: 0, stdout: "enabled", stderr: "" };
    if (args.includes("restart")) {
      restarted = true;
      return { code: 0, stdout: "", stderr: "" };
    }
    return { code: 0, stdout: "", stderr: "" };
  };

  const frozen = () => ({ published_at: new Date(clk.get() - 999_999).toISOString() });
  const advancing = () => ({ published_at: new Date(clk.get()).toISOString() });

  // The first healthWait runs for WEDGE_PATIENCE_MS; mark patienceDone once virtual
  // time has advanced past it, so "recoverBeforeRestart" can flip fresh afterwards.
  const start = clk.get();
  const readSnapshot = () => {
    if (!patienceDone && clk.get() - start >= WEDGE_PATIENCE_MS) patienceDone = true;
    switch (mode) {
      case "busy":
        return advancing();
      case "wedgedThenHealthy":
        return restarted ? advancing() : frozen();
      case "wedgedForever":
        return frozen();
      case "recoverBeforeRestart":
        return patienceDone ? advancing() : frozen();
    }
  };

  const d = svc({
    now: clk.now,
    sleep: clk.sleep,
    readSnapshot,
    fileExists: () => true,
    writeFile: () => {},
    readFile: () => null,
    warn: () => {},
    run,
  });
  return { d, calls, restartedRef: () => restarted };
}

describe("daemon self-heal (F14: active + wedged → auto-restart once)", () => {
  test("busy daemon (snapshot advancing) attaches WITHOUT restart", async () => {
    const { d, calls } = harness("busy");
    const r = await d.ensureRunning();
    expect(r.healthy).toBe(true);
    expect(calls.some((c) => c.includes("restart"))).toBe(false);
  });

  test("wedged daemon is auto-restarted once, then attaches", async () => {
    const { d, calls } = harness("wedgedThenHealthy");
    const r = await d.ensureRunning();
    expect(r.healthy).toBe(true);
    const restarts = calls.filter((c) => c.includes("restart"));
    expect(restarts.length).toBe(1);
  });

  test("still wedged after restart → fail-closed (throws, no false attach)", async () => {
    const { d, calls } = harness("wedgedForever");
    await expect(d.ensureRunning()).rejects.toBeInstanceOf(DaemonStartError);
    // restart was attempted exactly once before giving up.
    expect(calls.filter((c) => c.includes("restart")).length).toBe(1);
  });

  test("recovers right before restart → race guard attaches, NO restart", async () => {
    const { d, calls } = harness("recoverBeforeRestart");
    const r = await d.ensureRunning();
    expect(r.healthy).toBe(true);
    expect(calls.some((c) => c.includes("restart"))).toBe(false);
  });
});

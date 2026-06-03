// F43 launcher version-skew self-heal: a daemon publishing a fresh snapshot may still be
// running STALE code (booted before a merge) — it silently rejects new console verbs (e.g.
// F38 `research`). The launcher stamps/compares git HEAD: snapshot.code_version vs working-tree
// HEAD. On a skew it restarts ONCE before attaching; biased fail-OPEN so it can never loop.
// Mirrors the injected-dep harness in launcher-f14.test.ts.

import { describe, expect, test } from "bun:test";
import { DaemonService, DaemonStartError, type DaemonDeps, type Runner } from "../launcher/daemon";

function makeClock() {
  let t = 1_000_000;
  return { now: () => t, get: () => t, sleep: async (ms: number) => { t += ms; } };
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

const LAUNCHER_SHA = "abc1234deadbeefabc1234deadbeefabc1234dea";

/**
 * Harness for the fresh-snapshot (attach-candidate) path.
 *  - daemonSha: `undefined` → snapshot stamps the SAME sha as the launcher (match);
 *               a string → stamps that value (skew if ≠ launcher, blank "" → unresolved);
 *               `null` → omits the code_version key entirely (pre-F43 daemon).
 *  - launcherSha: the `git rev-parse HEAD` result; "" makes git fail (HEAD unknown).
 *  - afterRestart: "healthy" → new daemon advances the snapshot; "frozen" → stays stuck.
 */
function harness(opts: {
  daemonSha?: string | null;
  launcherSha?: string;
  afterRestart?: "healthy" | "frozen";
}) {
  const clk = makeClock();
  const calls: string[] = [];
  let restarted = false;
  const launcherSha = opts.launcherSha ?? LAUNCHER_SHA;
  const afterRestart = opts.afterRestart ?? "healthy";

  const run: Runner = async (args: string[]) => {
    calls.push(args.join(" "));
    if (args.includes("rev-parse")) {
      return launcherSha
        ? { code: 0, stdout: launcherSha, stderr: "" }
        : { code: 128, stdout: "", stderr: "not a git repository" };
    }
    if (args.includes("is-active")) return { code: 0, stdout: "active", stderr: "" };
    if (args.includes("is-enabled")) return { code: 0, stdout: "enabled", stderr: "" };
    if (args.includes("restart")) { restarted = true; return { code: 0, stdout: "", stderr: "" }; }
    return { code: 0, stdout: "", stderr: "" };
  };

  const frozen = clk.get() - 999_999; // far in the past → never "advances"
  const readSnapshot = () => {
    const pub = restarted && afterRestart === "frozen" ? frozen : clk.get();
    const snap: Record<string, unknown> = { published_at: new Date(pub).toISOString() };
    if (opts.daemonSha !== null) {
      snap["code_version"] = opts.daemonSha === undefined ? launcherSha : opts.daemonSha;
    }
    return snap;
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
  return { d, calls, restarts: () => calls.filter((c) => c.includes("restart")).length };
}

describe("daemon self-heal (F43: fresh snapshot + stale code → auto-restart once)", () => {
  test("matching code_version attaches WITHOUT restart (AC-3)", async () => {
    const { d, restarts } = harness({ daemonSha: undefined });
    const r = await d.ensureRunning();
    expect(r.healthy).toBe(true);
    expect(restarts()).toBe(0);
  });

  test("skewed code_version → auto-restarted once, then healthy (AC-2)", async () => {
    const { d, restarts } = harness({ daemonSha: "0000000staleSHAstaleSHAstaleSHAstaleSHA0" });
    const r = await d.ensureRunning();
    expect(r.healthy).toBe(true);
    expect(restarts()).toBe(1);
    expect(r.reason).toContain("auto-restarted");
  });

  test("missing code_version key (pre-F43 daemon) → restarted once (AC-4)", async () => {
    const { d, restarts } = harness({ daemonSha: null });
    const r = await d.ensureRunning();
    expect(r.healthy).toBe(true);
    expect(restarts()).toBe(1);
  });

  test("launcher HEAD unknown (git fails) → fail-open, NO restart (AC-5 / G-1)", async () => {
    const { d, restarts } = harness({ daemonSha: "anySHAanySHAanySHAanySHAanySHAanySHAany0", launcherSha: "" });
    const r = await d.ensureRunning();
    expect(r.healthy).toBe(true);
    expect(restarts()).toBe(0);
  });

  test("daemon code_version blank (git unresolved on daemon) → NO restart loop", async () => {
    const { d, restarts } = harness({ daemonSha: "" });
    const r = await d.ensureRunning();
    expect(r.healthy).toBe(true);
    expect(restarts()).toBe(0);
  });

  test("skew restart issued but snapshot stays frozen → fail-closed (throws, one restart) (G-2)", async () => {
    const { d, restarts } = harness({
      daemonSha: "0000000staleSHAstaleSHAstaleSHAstaleSHA0",
      afterRestart: "frozen",
    });
    await expect(d.ensureRunning()).rejects.toBeInstanceOf(DaemonStartError);
    expect(restarts()).toBe(1);
  });
});

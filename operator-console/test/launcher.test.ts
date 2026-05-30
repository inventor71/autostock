// F5 launcher unit tests (bun test). Pure + injectable-dep coverage for config/preflight/
// unit-template/daemon. No secrets asserted by value; systemctl/snapshot are mocked.

import { describe, expect, test } from "bun:test";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { consoleEnv, parseDotenv, resolveConfig, TOKEN_KEY } from "../launcher/config";
import { formatReport, runPreflight } from "../launcher/preflight";
import { renderUnit } from "../launcher/unit-template";
import { DaemonService, DaemonStartError, publishedAtMs, type DaemonDeps } from "../launcher/daemon";

function tmp(): string {
  return mkdtempSync(join(tmpdir(), "f5-"));
}

/** Build a fake project root with .env (token) + steering dir + mcp-server.ts. */
function fakeRoot(token = "tok-canon", consoleToken?: string): string {
  const root = tmp();
  writeFileSync(join(root, ".env"), `STEERING_OPERATOR_TOKEN=${token}\n`);
  mkdirSync(join(root, "steering"), { recursive: true });
  mkdirSync(join(root, "operator-console", "src"), { recursive: true });
  writeFileSync(join(root, "operator-console", "src", "mcp-server.ts"), "// stub\n");
  if (consoleToken !== undefined) {
    mkdirSync(join(root, "operator-console", "cli"), { recursive: true });
    writeFileSync(join(root, "operator-console", "cli", ".env"), `STEERING_OPERATOR_TOKEN=${consoleToken}\n`);
  }
  return root;
}

describe("config.parseDotenv", () => {
  test("handles export, quotes, comments, blanks", () => {
    const m = parseDotenv(['# a comment', 'export FOO=bar', 'QUOTED="hello world"', "SQ='x'", "", "BAD", "K=v=w"].join("\n"));
    expect(m.FOO).toBe("bar");
    expect(m.QUOTED).toBe("hello world");
    expect(m.SQ).toBe("x");
    expect(m.K).toBe("v=w");
    expect("BAD" in m).toBe(false);
  });
});

describe("config.resolveConfig", () => {
  test("derives paths + reads canonical token from root .env", () => {
    const root = fakeRoot("abc123");
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: root }, home: "/home/u" });
    expect(cfg.autostockRoot).toBe(root);
    expect(cfg.steeringDir).toBe(join(root, "steering"));
    expect(cfg.consoleCwd).toBe(join(root, "operator-console", "cli"));
    expect(cfg.mcpServerPath).toBe(join(root, "operator-console", "src", "mcp-server.ts"));
    expect(cfg.installPath).toBe("/home/u/.local/bin/autostock");
    expect(cfg.token).toBe("abc123");
  });

  test("an already-exported token overrides the file", () => {
    const root = fakeRoot("fromfile");
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: root, [TOKEN_KEY]: "fromenv" } });
    expect(cfg.token).toBe("fromenv");
  });
});

describe("config.consoleEnv (critic2 #2 — full inject set)", () => {
  test("injects AUTOSTOCK_ROOT + STEERING_DIR + token + LOCKDOWN", () => {
    const root = fakeRoot("t");
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: root } });
    const env = consoleEnv(cfg, {});
    expect(env.AUTOSTOCK_ROOT).toBe(root);
    expect(env.STEERING_DIR).toBe(join(root, "steering"));
    expect(env[TOKEN_KEY]).toBe("t");
    expect(env.AUTOSTOCK_LOCKDOWN).toBe("on");
  });
});

describe("preflight.runPreflight", () => {
  test("all green → ok", () => {
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: fakeRoot() } });
    const r = runPreflight(cfg);
    expect(r.ok).toBe(true);
    expect(r.checks.find((c) => c.id === "mcp_path")?.status).toBe("pass");
  });

  test("missing token → blocking fail, not ok, value never echoed", () => {
    const root = fakeRoot();
    writeFileSync(join(root, ".env"), "OTHER=1\n"); // no token
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: root } });
    const r = runPreflight(cfg);
    expect(r.ok).toBe(false);
    const c = r.checks.find((x) => x.id === "token_canonical")!;
    expect(c.status).toBe("fail");
    expect(c.remediation).toContain("STEERING_OPERATOR_TOKEN");
  });

  test("token drift → warn but still ok", () => {
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: fakeRoot("canon", "other") } });
    const r = runPreflight(cfg);
    expect(r.ok).toBe(true);
    expect(r.checks.find((c) => c.id === "token_drift")?.status).toBe("warn");
  });

  test("missing mcp-server.ts → blocking fail (silent-MCP guard)", () => {
    const root = fakeRoot();
    // remove the mcp file by pointing at a root without it
    const root2 = tmp();
    writeFileSync(join(root2, ".env"), "STEERING_OPERATOR_TOKEN=t\n");
    mkdirSync(join(root2, "steering"), { recursive: true });
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: root2 } });
    const r = runPreflight(cfg);
    expect(r.ok).toBe(false);
    expect(r.checks.find((c) => c.id === "mcp_path")?.status).toBe("fail");
    void root;
  });

  test("formatReport contains no remediation arrow when all pass", () => {
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: fakeRoot() } });
    expect(formatReport(runPreflight(cfg))).not.toContain("→");
  });
});

describe("unit-template.renderUnit (critic2 #3/#4)", () => {
  const u = renderUnit({ autostockRoot: "/r", python: "/r/.venv/bin/python" });
  test("WorkingDirectory present (load_dotenv CWD-relative)", () => {
    expect(u).toContain("WorkingDirectory=/r");
  });
  test("ExecStart runs main.py --mode agent --steering", () => {
    expect(u).toContain("ExecStart=/r/.venv/bin/python /r/main.py --mode agent --steering");
  });
  test("NO EnvironmentFile (systemd parser != dotenv)", () => {
    expect(u).not.toContain("EnvironmentFile");
  });
  test("Restart=on-failure + WantedBy", () => {
    expect(u).toContain("Restart=on-failure");
    expect(u).toContain("WantedBy=default.target");
  });
});

describe("daemon.publishedAtMs (critic2 #6 — naive-local)", () => {
  test("parses local ISO; null/absent → NaN", () => {
    expect(Number.isNaN(publishedAtMs(null))).toBe(true);
    expect(Number.isNaN(publishedAtMs({}))).toBe(true);
    const iso = new Date(1_700_000_000_000).toISOString().replace("Z", "");
    expect(publishedAtMs({ published_at: iso })).not.toBeNaN();
  });
});

/** Controllable clock for health-wait tests. */
function fakeClock() {
  let t = 1_000_000;
  return {
    now: () => t,
    sleep: async (ms: number) => {
      t += ms;
    },
    set: (v: number) => {
      t = v;
    },
    get: () => t,
  };
}

function svc(deps: DaemonDeps) {
  const root = fakeRoot();
  const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: root }, home: tmp() });
  return new DaemonService(cfg, deps);
}

describe("daemon.healthWait (critic #1)", () => {
  test("advancing+fresh snapshot → healthy", async () => {
    const clk = fakeClock();
    const d = svc({
      now: clk.now,
      sleep: clk.sleep,
      // returns a published_at == current fake clock → advances as the clock advances
      readSnapshot: () => ({ published_at: new Date(clk.get()).toISOString() }),
      fileExists: () => true,
    });
    const r = await d.healthWait();
    expect(r.healthy).toBe(true);
  });

  test("stale snapshot (older than window) → wedged timeout", async () => {
    const clk = fakeClock();
    const stale = new Date(clk.get() - 100_000).toISOString(); // 100s old > 45s window
    const d = svc({
      now: clk.now,
      sleep: clk.sleep,
      readSnapshot: () => ({ published_at: stale }),
      fileExists: () => true,
    });
    const r = await d.healthWait();
    expect(r.healthy).toBe(false);
    expect(r.reason).toContain("wedged");
  });

  test("no snapshot at all → wedged timeout", async () => {
    const clk = fakeClock();
    const d = svc({ now: clk.now, sleep: clk.sleep, readSnapshot: () => null, fileExists: () => true });
    expect((await d.healthWait()).healthy).toBe(false);
  });

  test("fresh but FROZEN (not advancing) → wedged (dead-recent daemon, live-verify)", async () => {
    const clk = fakeClock();
    const frozen = new Date(clk.get()).toISOString(); // recent but never changes
    const d = svc({ now: clk.now, sleep: clk.sleep, readSnapshot: () => ({ published_at: frozen }), fileExists: () => true });
    expect((await d.healthWait()).healthy).toBe(false); // advance required, not just freshness
  });
});

describe("daemon.ensureRunning (health-first attach + systemd, live-verify hardening)", () => {
  function harness(opts: { state?: string; freshFrom?: "always" | "afterStart" | "never" }) {
    const clk = fakeClock();
    const calls: string[][] = [];
    let started = false;
    const run = async (args: string[]) => {
      calls.push(args);
      if (args.includes("is-active")) return { code: 0, stdout: opts.state ?? "inactive", stderr: "" };
      if (args.includes("start")) started = true;
      return { code: 0, stdout: "", stderr: "" };
    };
    const readSnapshot = () => {
      const live = opts.freshFrom === "always" || (opts.freshFrom === "afterStart" && started);
      return live ? { published_at: new Date(clk.get()).toISOString() } : null;
    };
    const d = svc({ run, readSnapshot, now: clk.now, sleep: clk.sleep, fileExists: () => true });
    return { d, calls };
  }

  test("already running (fresh snapshot, e.g. a MANUAL daemon) → attach, NO systemctl start", async () => {
    const { d, calls } = harness({ state: "inactive", freshFrom: "always" });
    const r = await d.ensureRunning();
    expect(r.healthy).toBe(true);
    expect(r.reason).toContain("attached");
    expect(calls.some((c) => c.includes("start"))).toBe(false); // never double-start
  });

  test("down (no fresh snapshot) → systemctl start → healthy after it publishes", async () => {
    const { d, calls } = harness({ state: "inactive", freshFrom: "afterStart" });
    const r = await d.ensureRunning();
    expect(r.healthy).toBe(true);
    expect(calls.some((c) => c.includes("start"))).toBe(true);
  });

  test("failed unit + no fresh snapshot → throws DaemonStartError (no papering over)", async () => {
    const { d } = harness({ state: "failed", freshFrom: "never" });
    await expect(d.ensureRunning()).rejects.toBeInstanceOf(DaemonStartError);
  });
});

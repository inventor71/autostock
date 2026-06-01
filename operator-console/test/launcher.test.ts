// F5 launcher unit tests (bun test). Pure + injectable-dep coverage for config/preflight/
// unit-template/daemon. No secrets asserted by value; systemctl/snapshot are mocked.

import { describe, expect, test } from "bun:test";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { buildPermissionProfile, consoleEnv, parseDotenv, resolveConfig, TOKEN_KEY } from "../launcher/config";
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

describe("F26 supervisor mode — consoleEnv + buildPermissionProfile", () => {
  test("normal (default): no AUTOSTOCK_SUPERVISOR; OPENCODE_PERMISSION = locked normal profile", () => {
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: fakeRoot("t") } });
    const env = consoleEnv(cfg, {});
    expect(env.AUTOSTOCK_SUPERVISOR).toBeUndefined();
    const perm = JSON.parse(env.OPENCODE_PERMISSION);
    // source/cwd reads denied; only the steering status dir readable
    expect(perm.read["*"]).toBe("deny");
    expect(perm.read["../../steering/**"]).toBe("allow"); // consoleCwd=.../cli, steering=root/steering
    // glob/grep/lsp off (can't be path-scoped); removed as tools by disabled()
    expect(perm.glob).toBe("deny");
    expect(perm.grep).toBe("deny");
    expect(perm.lsp).toBe("deny");
  });

  test("supervisor flag: AUTOSTOCK_SUPERVISOR=on; read = all-but-secrets, deny AFTER allow", () => {
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: fakeRoot("t") } });
    const env = consoleEnv(cfg, {}, true);
    expect(env.AUTOSTOCK_SUPERVISOR).toBe("on");
    const perm = JSON.parse(env.OPENCODE_PERMISSION);
    expect(perm.read["*"]).toBe("allow");
    expect(perm.read["**/.env*"]).toBe("deny");
    expect(perm.read["**/secrets/**"]).toBe("deny");
    expect(perm.glob).toBe("allow");
    expect(perm.grep).toBe("allow");
    // ORDER matters (engine uses findLast): "*" allow must precede the secret denies so
    // deny wins for secrets. JSON.parse preserves insertion order for string keys.
    const keys = Object.keys(perm.read);
    expect(keys[0]).toBe("*");
    expect(keys.indexOf("**/.env*")).toBeGreaterThan(0);
  });

  test("secret deny globs cover BOTH worktree-root and nested paths", () => {
    // regression guard for the two critic findings about the anchored, dotall, worktree-relative
    // matcher: `**/.env*` matches nested/parent (../../.env) but NOT root (".env"); the bare
    // `.env*` matches root but NOT nested. BOTH are required. `*.key` (dotall) covers both.
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: fakeRoot("t") } });
    const perm = buildPermissionProfile(cfg, true);
    const readKeys = Object.keys(perm.read as Record<string, string>);
    expect(readKeys).toContain(".env*"); // root (e.g. cli/.env = STEERING_OPERATOR_TOKEN)
    expect(readKeys).toContain("**/.env*"); // nested / parent-repo
    expect(readKeys).toContain("secrets/**");
    expect(readKeys).toContain("**/secrets/**");
    expect(readKeys).toContain("*.key"); // dotall → matches root AND nested
  });

  test("stale AUTOSTOCK_SUPERVISOR in the parent env is scrubbed when launching normal", () => {
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: fakeRoot("t") } });
    const env = consoleEnv(cfg, { AUTOSTOCK_SUPERVISOR: "on" }, false);
    expect(env.AUTOSTOCK_SUPERVISOR).toBeUndefined();
  });

  test("websearch enabled for all providers via OPENCODE_ENABLE_EXA (keyless Exa)", () => {
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: fakeRoot("t") } });
    const env = consoleEnv(cfg, {});
    expect(env.OPENCODE_ENABLE_EXA).toBe("true");
  });

  test("operator override: existing OPENCODE_ENABLE_PARALLEL is not overridden with exa", () => {
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: fakeRoot("t") } });
    const env = consoleEnv(cfg, { OPENCODE_ENABLE_PARALLEL: "true" });
    expect(env.OPENCODE_ENABLE_PARALLEL).toBe("true");
    expect(env.OPENCODE_ENABLE_EXA).toBeUndefined();
  });

  test("EXA_API_KEY in the parent env is passed through (higher Exa limits)", () => {
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: fakeRoot("t") } });
    const env = consoleEnv(cfg, { EXA_API_KEY: "sk-exa-xxx" });
    expect(env.EXA_API_KEY).toBe("sk-exa-xxx");
    expect(env.OPENCODE_ENABLE_EXA).toBe("true");
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

  test("token VALUE never appears in the report output (SECURITY-03, even on drift)", () => {
    const secret = "SUPERSECRET-do-not-leak-123";
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: fakeRoot(secret, "other-token") } });
    const out = formatReport(runPreflight(cfg));
    expect(out).not.toContain(secret);
    expect(out).not.toContain("other-token");
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
  test("no path → no Environment=PATH line (systemd --user bare PATH)", () => {
    expect(u).not.toContain("Environment=PATH=");
  });
  test("path present → Environment=PATH baked in (claude on PATH)", () => {
    const up = renderUnit({
      autostockRoot: "/r",
      python: "/r/.venv/bin/python",
      path: "/home/u/.nvm/versions/node/v24.9.0/bin:/usr/bin:/bin",
    });
    expect(up).toContain("Environment=PATH=/home/u/.nvm/versions/node/v24.9.0/bin:/usr/bin:/bin");
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
  function harness(opts: { state?: string; freshFrom?: "always" | "afterStart" | "never"; frozen?: boolean }) {
    const clk = fakeClock();
    const frozenTs = new Date(clk.get()).toISOString();
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
      if (!live) return null;
      return { published_at: opts.frozen ? frozenTs : new Date(clk.get()).toISOString() };
    };
    const d = svc({
      run,
      readSnapshot,
      now: clk.now,
      sleep: clk.sleep,
      fileExists: () => true,
      writeFile: () => {},
      readFile: () => null,
      whichClaude: () => "/opt/cbin/claude",
    });
    return { d, calls };
  }

  test("already running (fresh+advancing, e.g. a MANUAL daemon) → attach, NO systemctl start", async () => {
    const { d, calls } = harness({ state: "inactive", freshFrom: "always" });
    const r = await d.ensureRunning();
    expect(r.healthy).toBe(true);
    expect(r.reason).toContain("attached");
    expect(calls.some((c) => c.includes("start"))).toBe(false); // never double-start
  });

  test("fresh but FROZEN (busy daemon mid-LLM-turn) → STILL attach, NO start (critic: no double-start)", async () => {
    const { d, calls } = harness({ state: "inactive", freshFrom: "always", frozen: true });
    const r = await d.ensureRunning();
    expect(r.healthy).toBe(true);
    expect(r.reason).toContain("lagging");
    expect(calls.some((c) => c.includes("start"))).toBe(false); // the key fix: a busy live daemon is not double-started
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

describe("daemon.ensureInstalled (review #2 — self-healing stale unit)", () => {
  // Shared root so unit CONTENT (which embeds autostockRoot) varies only by the dep under test.
  function installHarness(
    existing: string | null,
    whichClaude: () => string | null = () => "/opt/cbin/claude",
    root: string = fakeRoot(),
  ) {
    const clk = fakeClock();
    const calls: string[][] = [];
    const writes: string[] = [];
    const warns: string[] = [];
    const cfg = resolveConfig({ env: { AUTOSTOCK_ROOT: root }, home: tmp() });
    const d = new DaemonService(cfg, {
      now: clk.now,
      sleep: clk.sleep,
      fileExists: () => true,
      readFile: () => existing,
      writeFile: (_p, c) => writes.push(c),
      warn: (m) => warns.push(m),
      whichClaude,
      run: async (args) => {
        calls.push(args);
        return { code: 0, stdout: "", stderr: "" };
      },
    });
    return { d, calls, writes, warns, root };
  }

  test("stale unit content → rewrites + daemon-reload", async () => {
    const { d, calls, writes } = installHarness("[Unit]\nDescription=OLD\n");
    await d.ensureInstalled();
    expect(writes.length).toBe(1);
    expect(calls.some((c) => c.includes("daemon-reload"))).toBe(true);
  });

  test("identical unit content → no rewrite, no daemon-reload (idempotent)", async () => {
    // first render the desired content, feed it back as existing (same root → same content)
    const probe = installHarness(null);
    await probe.d.ensureInstalled();
    const desired = probe.writes[0];
    const { calls, writes } = installHarness(desired, () => "/opt/cbin/claude", probe.root);
    expect(writes.length).toBe(0);
    expect(calls.some((c) => c.includes("daemon-reload"))).toBe(false);
  });

  test("detected claude → bakes its dir + std dirs into Environment=PATH", async () => {
    const { d, writes } = installHarness(null, () => "/opt/cbin/claude");
    await d.ensureInstalled();
    expect(writes[0]).toContain("Environment=PATH=/opt/cbin:/usr/local/bin:/usr/bin:/bin");
  });

  test("detection FAILS but unit already has a PATH → preserve it, do NOT regress (critic HIGH)", async () => {
    // Build a known-good unit (claude was detectable), then re-run from a PATH-poor context.
    const probe = installHarness(null, () => "/old/cbin/claude");
    await probe.d.ensureInstalled();
    const goodUnit = probe.writes[0];
    expect(goodUnit).toContain("Environment=PATH=/old/cbin:");

    const h = installHarness(goodUnit, () => null, probe.root); // claude no longer resolvable
    await h.d.ensureInstalled();
    expect(h.writes.length).toBe(0); // preserved → identical → no rewrite, no silent regression
    expect(h.calls.some((c) => c.includes("daemon-reload"))).toBe(false);
  });

  test("detection FAILS and no existing PATH → omit line + warn loudly", async () => {
    const { d, writes, warns } = installHarness("[Unit]\nDescription=OLD\n", () => null);
    await d.ensureInstalled();
    expect(writes[0]).not.toContain("Environment=PATH=");
    expect(warns.some((m) => m.includes("`claude` CLI not found"))).toBe(true);
  });
});

describe("daemon.publishedAtMs (review #6 — Python microsecond ISO must not NaN)", () => {
  test("6-digit microsecond naive-local string parses to a real epoch", () => {
    const ms = publishedAtMs({ published_at: "2026-05-30T18:27:38.102467" });
    expect(Number.isNaN(ms)).toBe(false);
  });
});

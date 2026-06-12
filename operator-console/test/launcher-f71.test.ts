// F71 U1 — `autostock serve`/`qr`: password fail-closed, tailnet-only bind, pairing payload.
import { describe, expect, test } from "bun:test";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  buildPairingPayload,
  detectTailscaleIp,
  resolveServeContext,
  resolveServePassword,
  serveArgs,
  serveEnv,
  ServeConfigError,
  PASSWORD_KEY,
  SERVE_PORT,
  type Exec,
} from "../launcher/serve";
import { renderServeUnit, SERVE_UNIT_NAME } from "../launcher/unit-template";
import type { LauncherConfig } from "../launcher/config";

function tmpRoot(envText?: string): string {
  const dir = mkdtempSync(join(tmpdir(), "f71-"));
  if (envText !== undefined) writeFileSync(join(dir, ".env"), envText, "utf8");
  return dir;
}

const okExec: Exec = async (cmd) =>
  cmd[0] === "tailscale" ? { code: 0, stdout: "100.101.102.103\n" } : { code: 127, stdout: "" };
const noTsExec: Exec = async () => ({ code: 1, stdout: "" });

function fakeCfg(root: string): LauncherConfig {
  return {
    autostockRoot: root,
    steeringDir: join(root, "steering"),
    mcpServerPath: join(root, "operator-console/src/mcp-server.ts"),
    consoleCwd: join(root, "operator-console/cli"),
    consoleEnvPath: join(root, "operator-console/cli/.env"),
    installPath: join(root, ".local/bin/autostock"),
    token: "tok",
    consoleToken: "",
  } as unknown as LauncherConfig;
}

describe("resolveServePassword", () => {
  test("process env wins over .env", () => {
    const root = tmpRoot(`${PASSWORD_KEY}=fromfile\n`);
    expect(resolveServePassword({ autostockRoot: root }, { [PASSWORD_KEY]: "fromenv" })).toBe("fromenv");
  });
  test("falls back to root .env", () => {
    const root = tmpRoot(`${PASSWORD_KEY}=s3cret\n`);
    expect(resolveServePassword({ autostockRoot: root }, {})).toBe("s3cret");
  });
  test("empty when neither set", () => {
    const root = tmpRoot("");
    expect(resolveServePassword({ autostockRoot: root }, {})).toBe("");
  });
});

describe("resolveServeContext (fail-closed)", () => {
  test("throws without password — server must never start unsecured", async () => {
    const cfg = fakeCfg(tmpRoot(""));
    await expect(resolveServeContext(cfg, {}, okExec)).rejects.toBeInstanceOf(ServeConfigError);
  });
  test("throws without tailscale — never falls back to 0.0.0.0", async () => {
    const cfg = fakeCfg(tmpRoot(`${PASSWORD_KEY}=pw\n`));
    await expect(resolveServeContext(cfg, {}, noTsExec)).rejects.toBeInstanceOf(ServeConfigError);
  });
  test("resolves url from tailscale ip", async () => {
    const cfg = fakeCfg(tmpRoot(`${PASSWORD_KEY}=pw\n`));
    const ctx = await resolveServeContext(cfg, {}, okExec);
    expect(ctx.url).toBe(`http://100.101.102.103:${SERVE_PORT}`);
    expect(ctx.hostname).toBe("100.101.102.103");
  });
});

describe("detectTailscaleIp", () => {
  test("parses first ipv4 line", async () => {
    expect(await detectTailscaleIp(okExec)).toBe("100.101.102.103");
  });
  test("null on failure / garbage", async () => {
    expect(await detectTailscaleIp(noTsExec)).toBeNull();
    expect(await detectTailscaleIp(async () => ({ code: 0, stdout: "not-an-ip\n" }))).toBeNull();
  });
});

describe("buildPairingPayload", () => {
  test("roundtrips url+password with version", () => {
    const parsed = JSON.parse(buildPairingPayload("http://100.1.2.3:4096", "pw!"));
    expect(parsed).toEqual({ v: 1, kind: "autostock-pair", url: "http://100.1.2.3:4096", password: "pw!" });
  });
});

describe("serveArgs / serveEnv", () => {
  test("binds the given hostname only (tailnet interface)", () => {
    expect(serveArgs("100.1.2.3")).toEqual(["serve", "--port", "4096", "--hostname", "100.1.2.3"]);
  });
  test("env carries TUI wiring + password, never supervisor", () => {
    const cfg = fakeCfg(tmpRoot(""));
    const env = serveEnv(cfg, { PATH: "/bin" }, "pw");
    expect(env[PASSWORD_KEY]).toBe("pw");
    expect(env.STEERING_DIR).toBe(cfg.steeringDir);
    expect(env.AUTOSTOCK_ROOT).toBe(cfg.autostockRoot);
    expect(env.STEERING_OPERATOR_TOKEN).toBe("tok");
  });
});

describe("renderServeUnit", () => {
  test("unit runs the launcher serve subcommand (single code path)", () => {
    const text = renderServeUnit({ autostockRoot: "/r", shimPath: "/home/u/.local/bin/autostock", path: "/b:/usr/bin" });
    expect(SERVE_UNIT_NAME).toBe("autostock-serve.service");
    expect(text).toContain("ExecStart=/home/u/.local/bin/autostock serve");
    expect(text).toContain("WorkingDirectory=/r");
    expect(text).toContain("Restart=on-failure");
    expect(text).toContain("Environment=PATH=/b:/usr/bin");
  });
  test("omits PATH line when not given", () => {
    const text = renderServeUnit({ autostockRoot: "/r", shimPath: "/s" });
    expect(text).not.toContain("Environment=PATH");
  });
});

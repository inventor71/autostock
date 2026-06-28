// F71 U1 — `autostock serve`/`qr`: password fail-closed, tailnet-only bind, pairing payload.
import { describe, expect, test } from "bun:test";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import fc from "fast-check";
import {
  buildPairingPayload,
  detectTailscaleIp,
  resolveServeContext,
  resolveServePassword,
  resolveWebauthnOrigin,
  runQr,
  serveArgs,
  serveEnv,
  ServeConfigError,
  PASSWORD_KEY,
  WEBAUTHN_ORIGIN_KEY,
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

// ── F93 ──────────────────────────────────────────────────────────────────────
// R2: serve must forward AUTOSTOCK_WEBAUTHN_ORIGIN from .env (the shim only exports AUTOSTOCK_ROOT;
//     consoleEnv is a pure process.env passthrough). Mirrors resolveServePassword precedence.
describe("resolveWebauthnOrigin (R2)", () => {
  test("process env wins over .env", () => {
    const root = tmpRoot(`${WEBAUTHN_ORIGIN_KEY}=https://file.ts.net\n`);
    expect(resolveWebauthnOrigin({ autostockRoot: root }, { [WEBAUTHN_ORIGIN_KEY]: "https://env.ts.net" })).toBe(
      "https://env.ts.net",
    );
  });
  test("falls back to root .env", () => {
    const root = tmpRoot(`${WEBAUTHN_ORIGIN_KEY}=https://file.ts.net\n`);
    expect(resolveWebauthnOrigin({ autostockRoot: root }, {})).toBe("https://file.ts.net");
  });
  test("empty when neither set (server stays fail-closed)", () => {
    expect(resolveWebauthnOrigin({ autostockRoot: tmpRoot("") }, {})).toBe("");
  });
});

describe("serveEnv — WebAuthn origin forwarding (R2)", () => {
  test("injects origin from .env when not in the process env", () => {
    const cfg = fakeCfg(tmpRoot(`${WEBAUTHN_ORIGIN_KEY}=https://pc.ts.net\n`));
    const env = serveEnv(cfg, { PATH: "/bin" }, "pw");
    expect(env[WEBAUTHN_ORIGIN_KEY]).toBe("https://pc.ts.net");
  });
  test("process env wins over .env", () => {
    const cfg = fakeCfg(tmpRoot(`${WEBAUTHN_ORIGIN_KEY}=https://file.ts.net\n`));
    const env = serveEnv(cfg, { [WEBAUTHN_ORIGIN_KEY]: "https://env.ts.net" }, "pw");
    expect(env[WEBAUTHN_ORIGIN_KEY]).toBe("https://env.ts.net");
  });
  test("stays unset when neither has it (fail-closed, no empty injection)", () => {
    const cfg = fakeCfg(tmpRoot(""));
    const env = serveEnv(cfg, { PATH: "/bin" }, "pw");
    expect(env[WEBAUTHN_ORIGIN_KEY]).toBeUndefined();
  });
});

// R3: QR/pairing must prefer the https origin (passkeys need a secure context; an https page cannot
//     call an http API). resolveServeContext surfaces it; runQr pairs against it with an http fallback.
describe("resolveServeContext — webauthnOrigin (R3)", () => {
  test("surfaces the resolved origin alongside the raw bind url", async () => {
    const cfg = fakeCfg(tmpRoot(`${PASSWORD_KEY}=pw\n${WEBAUTHN_ORIGIN_KEY}=https://pc.ts.net\n`));
    const ctx = await resolveServeContext(cfg, {}, okExec);
    expect(ctx.url).toBe(`http://100.101.102.103:${SERVE_PORT}`); // bind stays the tailnet interface
    expect(ctx.webauthnOrigin).toBe("https://pc.ts.net");
  });
});

describe("runQr — https pairing (R3)", () => {
  async function capture(envText: string): Promise<string> {
    const cfg = fakeCfg(tmpRoot(envText));
    let out = "";
    await runQr(cfg, {}, okExec, (s) => (out += s));
    return out;
  }
  test("pairs against the https origin when set (not the raw http bind url)", async () => {
    const out = await capture(`${PASSWORD_KEY}=pw\n${WEBAUTHN_ORIGIN_KEY}=https://pc.ts.net\n`);
    expect(out).toContain("서버: https://pc.ts.net");
    expect(out).not.toContain(`서버: http://100.101.102.103:${SERVE_PORT}`);
    expect(out).not.toContain(`${WEBAUTHN_ORIGIN_KEY} 미설정`);
  });
  test("falls back to the http bind url with a warning when origin unset", async () => {
    const out = await capture(`${PASSWORD_KEY}=pw\n`);
    expect(out).toContain(`서버: http://100.101.102.103:${SERVE_PORT}`);
    expect(out).toContain(`${WEBAUTHN_ORIGIN_KEY} 미설정`);
  });
  test("the pairing payload (QR contents) carries the chosen url", async () => {
    // buildPairingPayload bakes the url the phone connects to — assert the https origin lands there.
    const cfg = fakeCfg(tmpRoot(`${PASSWORD_KEY}=pw\n${WEBAUTHN_ORIGIN_KEY}=https://pc.ts.net\n`));
    const ctx = await resolveServeContext(cfg, {}, okExec);
    const parsed = JSON.parse(buildPairingPayload(ctx.webauthnOrigin || ctx.url, ctx.password));
    expect(parsed.url).toBe("https://pc.ts.net");
  });
});

// PBT (Partial: PBT-02 round-trip, PBT-07 generators, PBT-08 shrinking via fast-check defaults).
// The pairing payload is the QR↔phone contract FR-3 depends on: encoding then JSON-decoding must
// recover the exact url+password for ANY strings (unicode, separators, empty).
describe("buildPairingPayload — round-trip property (PBT-02)", () => {
  test("JSON.parse(build(url, pw)) recovers {v,kind,url,password} for arbitrary inputs", () => {
    fc.assert(
      fc.property(fc.string(), fc.string(), (url, password) => {
        const parsed = JSON.parse(buildPairingPayload(url, password));
        expect(parsed).toEqual({ v: 1, kind: "autostock-pair", url, password });
      }),
    );
  });
});

// F71 U1 — `autostock serve` / `autostock qr`: headless opencode server for the phone PWA.
//
// Security posture (Security Baseline, US-5/US-7):
//  - OPENCODE_SERVER_PASSWORD is MANDATORY — without it `opencode serve` runs unsecured, so we
//    fail closed here instead of inheriting that foot-gun.
//  - The server binds the *tailscale interface IP only* (never 0.0.0.0): off-tailnet peers can't
//    even reach the socket (US-7 AC3 is structural, not advisory).
//  - The pairing QR (URL+password, US-1) renders ON DEMAND to the terminal and is never logged.

import { join } from "node:path";
import { readEnvKey, consoleEnv, type LauncherConfig } from "./config";

export const PASSWORD_KEY = "OPENCODE_SERVER_PASSWORD";
export const WEBAUTHN_ORIGIN_KEY = "AUTOSTOCK_WEBAUTHN_ORIGIN";
export const SERVE_PORT = 4096;

/** Resolve the server password: process env wins, then the root .env. Empty → fail-closed. */
export function resolveServePassword(
  cfg: Pick<LauncherConfig, "autostockRoot">,
  env: Record<string, string | undefined> = process.env,
): string {
  const fromEnv = env[PASSWORD_KEY] ?? "";
  if (fromEnv) return fromEnv;
  return readEnvKey(join(cfg.autostockRoot, ".env"), PASSWORD_KEY);
}

/**
 * Resolve the WebAuthn https origin (the *.ts.net origin the phone loads the PWA from): process env
 * wins, then the root .env. Empty → unset (webauthn verification stays fail-closed server-side).
 * F93: the shim only exports AUTOSTOCK_ROOT and `consoleEnv` is a pure process.env passthrough, so
 * without this the origin set in `.env` never reached the serve process and passkeys fail-closed.
 */
export function resolveWebauthnOrigin(
  cfg: Pick<LauncherConfig, "autostockRoot">,
  env: Record<string, string | undefined> = process.env,
): string {
  const fromEnv = env[WEBAUTHN_ORIGIN_KEY] ?? "";
  if (fromEnv) return fromEnv;
  return readEnvKey(join(cfg.autostockRoot, ".env"), WEBAUTHN_ORIGIN_KEY);
}

export type ExecResult = { code: number; stdout: string };
export type Exec = (cmd: string[]) => Promise<ExecResult>;

const defaultExec: Exec = async (cmd) => {
  try {
    // @ts-ignore Bun global
    const proc = Bun.spawn(cmd, { stdout: "pipe", stderr: "ignore" });
    const stdout = await new Response(proc.stdout).text();
    return { code: await proc.exited, stdout };
  } catch {
    return { code: 127, stdout: "" };
  }
};

/** First IPv4 from `tailscale ip -4`, or null (not installed / not logged in). */
export async function detectTailscaleIp(exec: Exec = defaultExec): Promise<string | null> {
  const r = await exec(["tailscale", "ip", "-4"]);
  if (r.code !== 0) return null;
  const line = r.stdout.split("\n").map((l) => l.trim()).find(Boolean) ?? "";
  return /^\d{1,3}(\.\d{1,3}){3}$/.test(line) ? line : null;
}

/** Pairing payload the PWA's QR scanner consumes (US-1). Pure. */
export function buildPairingPayload(url: string, password: string): string {
  return JSON.stringify({ v: 1, kind: "autostock-pair", url, password });
}

/** Env for the serve process: same MCP/steering wiring as the TUI + the server password. */
export function serveEnv(
  cfg: LauncherConfig,
  base: Record<string, string | undefined> = process.env,
  password: string,
): Record<string, string> {
  const out = consoleEnv(cfg, base, false); // never supervisor on the network surface
  out[PASSWORD_KEY] = password;
  // F93: forward the WebAuthn https origin from the root .env when it isn't already exported, so the
  // server can verify passkey assertions (without it, expectedOrigin() is null → fail-closed).
  if (!out[WEBAUTHN_ORIGIN_KEY]) {
    const origin = resolveWebauthnOrigin(cfg, base);
    if (origin) out[WEBAUTHN_ORIGIN_KEY] = origin;
  }
  return out;
}

/** argv for `opencode serve` bound to the tailnet interface only. */
export function serveArgs(hostname: string, port: number = SERVE_PORT): string[] {
  return ["serve", "--port", String(port), "--hostname", hostname];
}

export class ServeConfigError extends Error {}

/** Resolve everything `autostock serve`/`qr` needs; throws ServeConfigError (fail-closed). */
export async function resolveServeContext(
  cfg: LauncherConfig,
  env: Record<string, string | undefined> = process.env,
  exec: Exec = defaultExec,
): Promise<{ password: string; hostname: string; url: string; webauthnOrigin: string }> {
  const password = resolveServePassword(cfg, env);
  if (!password) {
    throw new ServeConfigError(
      `${PASSWORD_KEY} 미설정 — 모바일 서버는 비번 없이 띄울 수 없습니다(fail-closed). ` +
        `루트 .env에 ${PASSWORD_KEY}=<비번> 을 추가하세요.`,
    );
  }
  const hostname = await detectTailscaleIp(exec);
  if (!hostname) {
    throw new ServeConfigError(
      "tailscale IPv4 를 찾지 못했습니다 — 모바일 서버는 tailnet 인터페이스에만 바인드합니다. " +
        "`tailscale up` 후 다시 시도하세요. (공개 바인드 0.0.0.0 은 지원하지 않음)",
    );
  }
  return {
    password,
    hostname,
    url: `http://${hostname}:${SERVE_PORT}`,
    webauthnOrigin: resolveWebauthnOrigin(cfg, env),
  };
}

/** `autostock qr` — render the pairing QR to the terminal. On-demand only; never logged. */
export async function runQr(
  cfg: LauncherConfig,
  env: Record<string, string | undefined> = process.env,
  exec: Exec = defaultExec,
  write: (s: string) => void = (s) => process.stdout.write(s),
): Promise<void> {
  const ctx = await resolveServeContext(cfg, env, exec);
  // F93: pair against the https origin (tailscale serve *.ts.net) when set — passkeys require a
  // secure context, and an https page cannot call an http API (mixed-content). Fall back to the raw
  // http bind url with a warning when the origin isn't configured yet.
  const pairingUrl = ctx.webauthnOrigin || ctx.url;
  const payload = buildPairingPayload(pairingUrl, ctx.password);
  const qrcode = await import("qrcode-terminal");
  await new Promise<void>((resolve) => {
    (qrcode.default ?? qrcode).generate(payload, { small: true }, (q: string) => {
      write(q + "\n");
      resolve();
    });
  });
  write(`서버: ${pairingUrl}\n`);
  if (!ctx.webauthnOrigin) {
    write(
      `⚠ ${WEBAUTHN_ORIGIN_KEY} 미설정 — http URL로 페어링됩니다. 패스키(승인/잠금)는 https 보안 ` +
        `컨텍스트에서만 동작하므로, tailscale serve로 https origin을 띄우고 루트 .env에 ` +
        `${WEBAUTHN_ORIGIN_KEY}=https://<host>.<tailnet>.ts.net 을 설정하세요.\n`,
    );
  }
  write("폰 PWA의 'QR로 서버 추가'로 스캔하세요. 비번이 포함되어 있으니 표시 후 화면을 지우세요.\n");
}

/** `autostock serve` — spawn the headless opencode server with TUI-equivalent wiring. */
export async function runServe(
  cfg: LauncherConfig,
  passthroughArgs: string[] = [],
  env: Record<string, string | undefined> = process.env,
  exec: Exec = defaultExec,
): Promise<number> {
  const ctx = await resolveServeContext(cfg, env, exec);
  const args = serveArgs(ctx.hostname);
  process.stderr.write(`autostock serve: ${ctx.url} (tailnet 전용 바인드, 비번 필수)\n`);
  // @ts-ignore Bun global
  const proc = Bun.spawn(["bun", "run", "dev", "--", ...args, ...passthroughArgs], {
    cwd: cfg.consoleCwd,
    env: serveEnv(cfg, env, ctx.password),
    stdin: "inherit",
    stdout: "inherit",
    stderr: "inherit",
  });
  return await proc.exited;
}

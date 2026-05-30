// F5 launcher — config resolution (E5 LauncherConfig).
// Resolves the env/paths the launcher needs BEFORE touching the daemon or console.
// SECURITY-03 (BR-6): token values live in memory only and are NEVER logged/printed.

import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";

export const TOKEN_KEY = "STEERING_OPERATOR_TOKEN";

/** Minimal dotenv-subset parser (KEY=VALUE; supports `export `, # comments, optional quotes).
 *  Returns a map; never logs values. Mirrors what python-dotenv accepts for our .env. */
export function parseDotenv(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const rawLine of text.split("\n")) {
    let line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    if (line.startsWith("export ")) line = line.slice("export ".length).trim();
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    if (!key) continue;
    let val = line.slice(eq + 1).trim();
    if (
      (val.startsWith('"') && val.endsWith('"') && val.length >= 2) ||
      (val.startsWith("'") && val.endsWith("'") && val.length >= 2)
    ) {
      val = val.slice(1, -1);
    }
    out[key] = val;
  }
  return out;
}

/** Read a single key from a .env file (returns "" if file/key absent). Never logs the value. */
export function readEnvKey(envPath: string, key: string): string {
  try {
    return parseDotenv(readFileSync(envPath, "utf8"))[key] ?? "";
  } catch {
    return "";
  }
}

export interface LauncherConfig {
  autostockRoot: string;
  steeringDir: string;
  consoleCwd: string; // operator-console/cli — `bun dev` must run from here (critic2 #2)
  mcpServerPath: string; // operator-console/src/mcp-server.ts
  rootEnvPath: string;
  consoleEnvPath: string; // operator-console/cli/.env (drift check)
  installPath: string; // ~/.local/bin/autostock
  /** canonical operator token from root .env (in-memory only; "" if absent). */
  token: string;
  /** console-side token from cli/.env, for drift detection only ("" if absent). */
  consoleToken: string;
}

/** Derive AUTOSTOCK_ROOT from the launcher file location when not exported.
 *  launcher/ lives at {ROOT}/operator-console/launcher, so root = ../../.. */
export function deriveRoot(launcherDir: string): string {
  return resolve(launcherDir, "..", "..");
}

export interface ResolveOpts {
  env?: Record<string, string | undefined>;
  /** directory of the launcher module (import.meta.dir); used to derive root if unset. */
  launcherDir?: string;
  home?: string;
}

export function resolveConfig(opts: ResolveOpts = {}): LauncherConfig {
  const env = opts.env ?? process.env;
  const home = opts.home ?? homedir();
  const autostockRoot = env.AUTOSTOCK_ROOT
    ? resolve(env.AUTOSTOCK_ROOT)
    : deriveRoot(opts.launcherDir ?? dirname(new URL(import.meta.url).pathname));

  const rootEnvPath = join(autostockRoot, ".env");
  const consoleCwd = join(autostockRoot, "operator-console", "cli");
  const consoleEnvPath = join(consoleCwd, ".env");
  const steeringDir = env.STEERING_DIR
    ? resolve(env.STEERING_DIR)
    : join(autostockRoot, "steering");

  // token: prefer an already-exported value (operator override), else canonical root .env.
  const token = env[TOKEN_KEY] || readEnvKey(rootEnvPath, TOKEN_KEY);
  const consoleToken = readEnvKey(consoleEnvPath, TOKEN_KEY);

  return {
    autostockRoot,
    steeringDir,
    consoleCwd,
    mcpServerPath: join(autostockRoot, "operator-console", "src", "mcp-server.ts"),
    rootEnvPath,
    consoleEnvPath,
    installPath: join(home, ".local", "bin", "autostock"),
    token,
    consoleToken,
  };
}

/** The env set the console MUST inherit so opencode's {env:...} MCP wiring resolves
 *  (critic2 #2): AUTOSTOCK_ROOT + STEERING_DIR + STEERING_OPERATOR_TOKEN, all absolute. */
export function consoleEnv(cfg: LauncherConfig, base: Record<string, string | undefined> = process.env): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(base)) if (v !== undefined) out[k] = v;
  out.AUTOSTOCK_ROOT = cfg.autostockRoot;
  out.STEERING_DIR = cfg.steeringDir;
  if (cfg.token) out[TOKEN_KEY] = cfg.token;
  out.AUTOSTOCK_LOCKDOWN = "on";
  return out;
}

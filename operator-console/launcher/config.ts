// F5 launcher — config resolution (E5 LauncherConfig).
// Resolves the env/paths the launcher needs BEFORE touching the daemon or console.
// SECURITY-03 (BR-6): token values live in memory only and are NEVER logged/printed.

import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";

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

/** F26 permission rule value: a single action, or a per-pattern map. Mirrors
 *  opencode's ConfigPermission.Rule (Action | Record<pattern, Action>). */
type PermAction = "allow" | "deny" | "ask";
type PermRule = PermAction | Record<string, PermAction>;
type PermProfile = Record<string, PermRule>;

/**
 * F26 — build the per-profile permission object injected via `OPENCODE_PERMISSION`
 * (opencode merges it into the static `opencode.json` at config load:
 *  flag.ts → process.env.OPENCODE_PERMISSION → config.ts mergeDeep). This is the
 * ONLY lever that differentiates normal vs supervisor; opencode's permission engine
 * is NOT patched.
 *
 * Two coordinate systems (verified against the fork):
 *  - `read`/`glob`/`grep` evaluate the file path **relative to the console worktree**
 *    (`read.ts` → `path.relative(instance.worktree, filepath)`; worktree = consoleCwd),
 *    so allow/deny globs here are worktree-relative.
 *  - `external_directory` evaluates an **absolute** dir glob (`external-directory.ts`),
 *    so its globs are absolute under autostockRoot/steeringDir.
 *
 * Rule ORDER matters: the engine uses `findLast` (last match wins). For supervisor we
 * put `"*": "allow"` first then secret denies (deny wins for secrets). For normal we put
 * `"*": "deny"` first then the steering allow last (steering wins). `glob`/`grep`/`lsp`
 * in normal are `"deny"` (a `{"*":"deny"}` shorthand) so `disabled()` removes the tools
 * entirely — they can't be path-scoped (their permission key is the search pattern), and
 * normal mode doesn't need source exploration. Secret globs use a globstar prefix
 * (`**` then slash) so they match the worktree-relative `../../.env` form (anchored
 * dotall matcher).
 */
export function buildPermissionProfile(cfg: LauncherConfig, supervisor: boolean): PermProfile {
  const steerRel = relative(cfg.consoleCwd, cfg.steeringDir).replaceAll("\\", "/");
  const root = cfg.autostockRoot.replaceAll("\\", "/");
  const steerAbs = cfg.steeringDir.replaceAll("\\", "/");

  if (!supervisor) {
    // Normal: only the steering status dir is readable; no source/cwd reads; no glob/grep/lsp.
    return {
      read: { "*": "deny", [`${steerRel}/**`]: "allow" },
      glob: "deny",
      grep: "deny",
      lsp: "deny",
      external_directory: { "*": "deny", [`${steerAbs}/**`]: "allow" },
    };
  }
  // Supervisor: whole repo readable EXCEPT secrets (deny last so it wins via findLast).
  // CRITICAL: `read` is evaluated on the path RELATIVE to the console worktree, and the
  // matcher is anchored+dotall (wildcard.ts). So a `**/`-prefixed glob ONLY matches paths
  // that contain a slash — it MISSES worktree-root files like `.env` (relative path ".env")
  // or `foo.key`. The cli worktree root holds `.env` (STEERING_OPERATOR_TOKEN), so we MUST
  // include slash-less variants too. `*.key`/`*.pem` need no `**/` variant — `*`→`.*` is
  // dotall, so `*.key` already matches BOTH "foo.key" and "../../a/foo.key".
  return {
    read: {
      "*": "allow",
      ".env*": "deny", // root-level (relative path has no slash)
      "**/.env*": "deny", // nested / parent-repo (../../.env)
      "*.key": "deny", // dotall — matches root AND nested
      "*.pem": "deny",
      "secrets/**": "deny",
      "**/secrets/**": "deny",
      "logs/**": "deny",
      "**/logs/**": "deny",
      ".git/**": "deny",
      "**/.git/**": "deny",
    },
    glob: "allow",
    grep: "allow",
    lsp: "allow",
    external_directory: {
      // external_directory matches an ABSOLUTE *parent-dir* glob (not the filename), so only
      // directory-level denies fire here; file-level secrets (.env/*.key) are caught by the
      // `read` layer above (authoritative content gate). Keep dir denies as defense-in-depth.
      "*": "deny",
      [`${root}/**`]: "allow",
      [`${root}/secrets/**`]: "deny",
      [`${root}/logs/**`]: "deny",
      [`${root}/.git/**`]: "deny",
    },
  };
}

/** The env set the console MUST inherit so opencode's {env:...} MCP wiring resolves
 *  (critic2 #2): AUTOSTOCK_ROOT + STEERING_DIR + STEERING_OPERATOR_TOKEN, all absolute.
 *  F26: also injects the supervisor flag + the per-profile permission set. */
export function consoleEnv(
  cfg: LauncherConfig,
  base: Record<string, string | undefined> = process.env,
  supervisor: boolean = false,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(base)) if (v !== undefined) out[k] = v;
  out.AUTOSTOCK_ROOT = cfg.autostockRoot;
  out.STEERING_DIR = cfg.steeringDir;
  if (cfg.token) out[TOKEN_KEY] = cfg.token;
  out.AUTOSTOCK_LOCKDOWN = "on";
  // F26: enable real web search for ALL providers. opencode gates `websearch` behind
  // webSearchEnabled() which is true only for the `opencode` provider OR the exa/parallel
  // flags (registry.ts) — with a direct Anthropic/etc. provider it would be silently
  // dropped. OPENCODE_ENABLE_EXA opens the gate; the Exa backend (mcp.exa.ai/mcp) works
  // KEYLESS, and if the operator sets EXA_API_KEY in the env it is passed through above
  // (copied from base) and Exa uses it for higher limits. webfetch is always available too.
  if (base.OPENCODE_ENABLE_PARALLEL === undefined && base.OPENCODE_ENABLE_EXA === undefined)
    out.OPENCODE_ENABLE_EXA = "true";
  // The console agent has no runtime tool to flip it (FR-4). Normal omits the flag.
  if (supervisor) out.AUTOSTOCK_SUPERVISOR = "on";
  else delete out.AUTOSTOCK_SUPERVISOR; // never inherit a stale value from the parent env
  out.OPENCODE_PERMISSION = JSON.stringify(buildPermissionProfile(cfg, supervisor));
  return out;
}

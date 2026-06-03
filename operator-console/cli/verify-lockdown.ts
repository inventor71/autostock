// Lockdown is defense-in-depth, in TWO layers:
//   1. PERMISSION (this script): our shipped opencode.json `permission` AND the per-profile
//      F26 permission sets (normal/supervisor) are checked against opencode's REAL permission
//      engine (Permission.fromConfig + evaluate) — deterministic, no LLM/TUI. Run from the fork
//      dir: bun run verify-lockdown.ts
//   2. COMPILE-TIME REMOVAL (F4 Phase 3): under AUTOSTOCK_LOCKDOWN=on the side-effect builtins
//      are not registered AT ALL (registry.ts), so opencode's permission bugs (#5894/#6396) are
//      structurally moot — not merely denied. That ABSENCE guarantee is asserted in
//      packages/opencode/test/tool/registry.test.ts ("autostock lockdown removes side-effect
//      builtins"). Run: bun test test/tool/registry.test.ts
// This script verifies layer 1; the registry test verifies layer 2.
import { readFileSync } from "node:fs";
import { disabled, evaluate, fromConfig } from "./packages/opencode/src/permission/index.ts";
import { buildPermissionProfile, type LauncherConfig } from "../launcher/config.ts";

let ok = true;
const check = (label: string, got: string, want: string) => {
  const pass = got === want;
  ok &&= pass;
  console.log(`[${pass ? "PASS" : "FAIL"}] ${label.padEnd(46)} got=${got} want=${want}`);
};

// ── Layer 1a: static opencode.json (profile-independent base: `*`:deny + MCP + web) ──
const cfgJson = JSON.parse(readFileSync(new URL("./opencode.json", import.meta.url), "utf8"));
const staticRules = fromConfig(cfgJson.permission);
const staticAct = (perm: string) => (evaluate as any)(perm, "*", staticRules).action;
console.log("── static opencode.json ──");
for (const [perm, want] of [
  // default-deny proves ANY non-allowlisted MUTATING tool is denied
  ["edit", "deny"], ["write", "deny"], ["bash", "deny"],
  ["task", "deny"], // closes the #5894 subagent bypass
  ["apply_patch", "deny"],
  ["some_random_unlisted_tool", "deny"],
  // F26: web tools are now allowed (restored under lockdown for research; FR-5)
  ["webfetch", "allow"], ["websearch", "allow"],
  // MCP tools
  ["autostock_steer", "ask"], ["autostock_steer_read", "allow"],
] as Array<[string, string]>) {
  check(`static ${perm}`, staticAct(perm), want);
}

// ── Layer 1b: F26 per-profile permission (normal / supervisor), with PATH cases ──
// Synthetic layout: AUTOSTOCK_ROOT=/root, console worktree=/root/operator-console/cli,
// STEERING_DIR=/root/steering. read/glob/grep evaluate worktree-RELATIVE paths;
// external_directory evaluates ABSOLUTE dir globs.
const fakeCfg = {
  autostockRoot: "/root",
  steeringDir: "/root/steering",
  consoleCwd: "/root/operator-console/cli",
} as unknown as LauncherConfig;

// Model the REAL runtime config: opencode.json `permission` merged with the profile
// (mirrors config.ts:746 `mergeDeep`), then fromConfig the single merged object — catches
// merge/key-order regressions an isolated-profile fromConfig would miss (critic MEDIUM).
// NOTE: every opencode.json permission value is a STRING and every profile-overridden key is
// an object/string the profile fully owns, so no key has objects on BOTH sides → remeda
// mergeDeep degenerates to a shallow `{...file, ...profile}` here (string→object replacement).
// We replicate that exactly (and avoid a remeda import that doesn't resolve from the cli root).
const mergeProfile = (sup: boolean) =>
  fromConfig({ ...cfgJson.permission, ...(buildPermissionProfile(fakeCfg, sup) as any) } as any);
const normal = mergeProfile(false);
const supervisor = mergeProfile(true);
const ev = (rules: any, perm: string, pat: string) => (evaluate as any)(perm, pat, rules).action;

console.log("── NORMAL profile ──");
// read: only the steering dir; cwd listing + source reads denied
check("normal read cwd-listing (\"\")", ev(normal, "read", ""), "deny");
check("normal read cwd-listing (.)", ev(normal, "read", "."), "deny");
check("normal read source (src/index.ts)", ev(normal, "read", "src/index.ts"), "deny");
check("normal read steering (../../steering/monitor.json)", ev(normal, "read", "../../steering/monitor.json"), "allow");
// glob/grep/lsp removed as TOOLS (can't be path-scoped); read survives (last rule != *:deny)
const normDisabled = disabled(["read", "glob", "grep", "lsp", "webfetch"], normal);
check("normal glob tool removed", String(normDisabled.has("glob")), "true");
check("normal grep tool removed", String(normDisabled.has("grep")), "true");
check("normal lsp tool removed", String(normDisabled.has("lsp")), "true");
check("normal read tool SURVIVES", String(normDisabled.has("read")), "false");
// external_directory: only steering (absolute) allowed
check("normal extdir steering /root/steering/*", ev(normal, "external_directory", "/root/steering/*"), "allow");
check("normal extdir source /root/src/*", ev(normal, "external_directory", "/root/src/*"), "deny");

console.log("── SUPERVISOR profile ──");
// read: whole repo EXCEPT secrets (worktree-relative paths)
check("sup read parent source (../../src/strategy/llm/client.py)", ev(supervisor, "read", "../../src/strategy/llm/client.py"), "allow");
check("sup read cli-internal (src/index.ts)", ev(supervisor, "read", "src/index.ts"), "allow");
check("sup read SECRET ../../.env", ev(supervisor, "read", "../../.env"), "deny");
check("sup read SECRET ../../logs/autostock.log", ev(supervisor, "read", "../../logs/autostock.log"), "deny");
check("sup read SECRET ../../secrets/x.key", ev(supervisor, "read", "../../secrets/x.key"), "deny");
check("sup read SECRET ../../.git/config", ev(supervisor, "read", "../../.git/config"), "deny");
// critic round-2 HIGH: worktree-ROOT secrets (relative path has NO slash) must ALSO be denied.
// cli/.env (= STEERING_OPERATOR_TOKEN) relative-resolves to ".env" — the bug case.
check("sup read SECRET root .env (cli token!)", ev(supervisor, "read", ".env"), "deny");
check("sup read SECRET root foo.key", ev(supervisor, "read", "foo.key"), "deny");
check("sup read SECRET root foo.pem", ev(supervisor, "read", "foo.pem"), "deny");
check("sup read SECRET root secrets/x.json", ev(supervisor, "read", "secrets/x.json"), "deny");
check("sup read SECRET root logs/x.log", ev(supervisor, "read", "logs/x.log"), "deny");
// glob/grep/lsp available again
const supDisabled = disabled(["read", "glob", "grep", "lsp"], supervisor);
check("sup glob tool available", String(supDisabled.has("glob")), "false");
check("sup grep tool available", String(supDisabled.has("grep")), "false");
// external_directory: root allowed, secret DIRS denied; mutating tools STILL absent
check("sup extdir source /root/src/x/*", ev(supervisor, "external_directory", "/root/src/x/*"), "allow");
check("sup extdir SECRET /root/secrets/*", ev(supervisor, "external_directory", "/root/secrets/*"), "deny");
check("sup extdir SECRET /root/logs/*", ev(supervisor, "external_directory", "/root/logs/*"), "deny");
// supervisor must NOT grant any mutating builtin. `supervisor` IS the merged config
// (opencode.json `*`:deny + profile), and the profile defines no edit/write/bash, so the
// top-level `*`:deny wins. Registry removal (layer 2) is the structural backstop.
check("sup edit deny (merged config)", ev(supervisor, "edit", "anything"), "deny");
check("sup write deny", ev(supervisor, "write", "anything"), "deny");
check("sup bash deny", ev(supervisor, "bash", "anything"), "deny");
check("sup task deny", ev(supervisor, "task", "anything"), "deny");

console.log(ok
  ? "\nRESULT: PASS ✅  lockdown + both F26 profiles verified against opencode's real permission engine"
  : "\nRESULT: FAIL ❌");
process.exit(ok ? 0 : 1);

// F5 launcher — preflight checks (E1/E2, P5). Pure judgments → PreflightCheck.
// fail-closed: any blocking fail aborts the launch with a diagnostic + remediation (BR-1).
// SECURITY-03 (BR-6): NEVER include token values in detail/remediation — boolean only.

import { existsSync } from "node:fs";
import type { LauncherConfig } from "./config";

export type CheckId = "token_canonical" | "token_drift" | "steering_dir" | "mcp_path";
export type CheckStatus = "pass" | "fail" | "warn";

export interface PreflightCheck {
  id: CheckId;
  label: string;
  status: CheckStatus;
  detail: string; // human one-liner — no secrets
  remediation?: string; // how to fix, when not pass
  blocking: boolean;
}

export interface PreflightReport {
  checks: PreflightCheck[];
  ok: boolean; // all blocking checks passed
}

/** Run all preflight checks against a resolved config. Pure (only reads fs existence). */
export function runPreflight(cfg: LauncherConfig): PreflightReport {
  const checks: PreflightCheck[] = [];

  // token_canonical (blocking) — value never shown, only presence.
  checks.push(
    cfg.token
      ? { id: "token_canonical", label: "operator token", status: "pass", detail: "canonical token present", blocking: true }
      : {
          id: "token_canonical",
          label: "operator token",
          status: "fail",
          detail: `no ${"STEERING_OPERATOR_TOKEN"} in ${cfg.rootEnvPath} (or env)`,
          remediation: `set STEERING_OPERATOR_TOKEN in ${cfg.rootEnvPath}`,
          blocking: true,
        },
  );

  // token_drift (warn only) — console .env disagreeing with canonical. Inject wins, so non-blocking.
  if (cfg.consoleToken && cfg.token && cfg.consoleToken !== cfg.token) {
    checks.push({
      id: "token_drift",
      label: "console token drift",
      status: "warn",
      detail: `${cfg.consoleEnvPath} token differs from canonical (launcher injects canonical)`,
      remediation: `align STEERING_OPERATOR_TOKEN in ${cfg.consoleEnvPath} with ${cfg.rootEnvPath}`,
      blocking: false,
    });
  }

  // steering_dir (blocking) — must exist or be creatable (parent exists).
  checks.push(
    existsSync(cfg.steeringDir)
      ? { id: "steering_dir", label: "steering dir", status: "pass", detail: cfg.steeringDir, blocking: true }
      : existsSync(cfg.autostockRoot)
        ? { id: "steering_dir", label: "steering dir", status: "pass", detail: `${cfg.steeringDir} (will be created)`, blocking: true }
        : {
            id: "steering_dir",
            label: "steering dir",
            status: "fail",
            detail: `AUTOSTOCK_ROOT not found: ${cfg.autostockRoot}`,
            remediation: "run autostock from the project, or export AUTOSTOCK_ROOT",
            blocking: true,
          },
  );

  // mcp_path (blocking) — the absolute MCP server path the console's {env:AUTOSTOCK_ROOT}
  // resolves to MUST exist, else autostock_steer never registers (silent "can't place orders").
  checks.push(
    existsSync(cfg.mcpServerPath)
      ? { id: "mcp_path", label: "MCP server", status: "pass", detail: cfg.mcpServerPath, blocking: true }
      : {
          id: "mcp_path",
          label: "MCP server",
          status: "fail",
          detail: `mcp-server.ts not found: ${cfg.mcpServerPath}`,
          remediation: "check AUTOSTOCK_ROOT; operator-console/src/mcp-server.ts must exist",
          blocking: true,
        },
  );

  const ok = checks.every((c) => !c.blocking || c.status === "pass");
  return { checks, ok };
}

/** Render a report for the terminal (no secrets). Used on abort. */
export function formatReport(report: PreflightReport): string {
  const glyph = (c: PreflightCheck) => (c.status === "pass" ? "✓" : c.status === "warn" ? "!" : "✗");
  const lines = report.checks.map((c) => {
    const head = `  ${glyph(c)} ${c.label}: ${c.detail}`;
    return c.status !== "pass" && c.remediation ? `${head}\n      → ${c.remediation}` : head;
  });
  return lines.join("\n");
}

#!/usr/bin/env bun
// F5 launcher — entry orchestration (P1). resolveConfig → preflight → ensureDaemon →
// launchConsole (TTY handoff, NO launcher-side watch — critic2 #1). Exit-code convention so a
// failure is NEVER silent (BR-1, SECURITY-15): 0 ok / 10 config / 11 preflight / 12 daemon /
// 13 console. Token values are never printed (BR-6).

import { consoleEnv, resolveConfig } from "./config";
import { DaemonService, DaemonStartError } from "./daemon";
import { formatReport, runPreflight } from "./preflight";
import { FileDrop } from "../src/filedrop";

export const EXIT = { OK: 0, CONFIG: 10, PREFLIGHT: 11, DAEMON: 12, CONSOLE: 13 } as const;

function die(code: number, msg: string): never {
  console.error(`autostock: ${msg}`);
  process.exit(code);
}

export async function main(): Promise<void> {
  // 1. config
  let cfg;
  try {
    cfg = resolveConfig({ launcherDir: import.meta.dir });
  } catch (e) {
    die(EXIT.CONFIG, `config 해석 실패: ${(e as Error).message}`);
  }

  // 2. preflight (fail-closed) — warnings printed, blocking failures abort.
  const report = runPreflight(cfg);
  for (const c of report.checks) {
    if (c.status === "warn") console.error(`autostock: warning — ${c.detail}${c.remediation ? `\n      → ${c.remediation}` : ""}`);
  }
  if (!report.ok) {
    console.error("autostock: preflight failed —\n" + formatReport(report));
    die(EXIT.PREFLIGHT, "위 항목을 해결한 뒤 다시 실행하세요.");
  }

  // 3. daemon: auto-start if down, attach if up (systemd --user).
  const fd = new FileDrop(cfg.steeringDir, cfg.token);
  const daemon = new DaemonService(cfg, { readSnapshot: () => fd.readSnapshot() });
  try {
    process.stderr.write("autostock: 데몬 확인…\n");
    const h = await daemon.ensureRunning();
    process.stderr.write(`autostock: 데몬 정상 (${h.reason}). 콘솔을 엽니다…\n`);
  } catch (e) {
    if (e instanceof DaemonStartError) die(EXIT.DAEMON, `데몬 기동 실패:\n      ${e.message}`);
    die(EXIT.DAEMON, `데몬 확인 중 오류: ${(e as Error).message}`);
  }

  // 4. launch console — TTY handoff (inherit stdio), session-first (Q1=A/critic2 #5 option B: -c).
  //    NO launcher-side watch loop after this; runtime-disconnect monitoring lives in the console.
  //    Forward any user args (e.g. `autostock -s ses_x` to resume a session); bare `autostock`
  //    passes none → opencode opens a FRESH home (no stale session), and the autostock sidebar
  //    renders on the home route (F5 option ②), so it is sidebar-first without resuming a session.
  const env = consoleEnv(cfg);
  const userArgs = process.argv.slice(2);
  const consoleArgs = userArgs;
  let code: number;
  try {
    // @ts-ignore Bun global
    const proc = Bun.spawn(["bun", "run", "dev", "--", ...consoleArgs], {
      cwd: cfg.consoleCwd,
      env,
      stdin: "inherit",
      stdout: "inherit",
      stderr: "inherit",
    });
    code = await proc.exited;
  } catch (e) {
    die(EXIT.CONSOLE, `콘솔 실행 실패 (cwd=${cfg.consoleCwd}): ${(e as Error).message}`);
  }
  process.exit(code === 0 ? EXIT.OK : code);
}

if (import.meta.main) {
  await main();
}

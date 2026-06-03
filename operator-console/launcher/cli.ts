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

const isSupervisorArg = (a: string) => a === "--supervisor" || a.startsWith("--supervisor=");
const isHelpArg = (a: string) => a === "-h" || a === "--help";

/** Single source of truth for launcher arg handling. `--supervisor` is the launcher's only
 *  OWNED flag → strip it so it never leaks to opencode's `.strict()` parser (it would reject it).
 *  `-h`/`--help` is DETECTED but KEPT in consoleArgs: the launcher prints its own section, then
 *  forwards the flag so opencode appends its full yargs help below (F40 loose-fuse). Everything
 *  else passes through untouched (opencode owns it; its `.strict()` rejects genuine unknowns). */
export function classifyArgs(userArgs: string[]): { supervisor: boolean; help: boolean; consoleArgs: string[] } {
  return {
    supervisor: userArgs.some(isSupervisorArg),
    help: userArgs.some(isHelpArg),
    consoleArgs: userArgs.filter((a) => !isSupervisorArg(a)),
  };
}

/** The launcher-owned help section (stderr). Documents the ONLY launcher flag (`--supervisor`)
 *  and the pass-through contract; opencode's own yargs help is printed right after (loose-fuse).
 *  Never emits secrets (BR-6). */
export function launcherHelpSection(): string {
  return [
    "autostock — AI 트레이딩 운영 콘솔 런처",
    "",
    "런처 옵션:",
    "  --supervisor   supervisor(read-only, 전체 코드 읽기) 프로파일로 진입.",
    "                 셸 접근이 있는 개발자 전용. 평상시엔 생략.",
    "  -h, --help     이 도움말을 표시.",
    "",
    "그 외 모든 인자는 opencode 콘솔로 그대로 전달됩니다 (예: autostock -s ses_x → 세션 재개).",
    "아래는 opencode 콘솔 자체 도움말입니다:",
    "─".repeat(60),
  ].join("\n");
}

/** F40 help path: print the launcher section, then hand the help flag to opencode so its full
 *  yargs help follows (loose-fuse). Runs BEFORE preflight/daemon — help must work even when the
 *  daemon is down. resolveConfig failure must NOT hard-fail help; we still exit 0. */
async function runHelp(consoleArgs: string[]): Promise<never> {
  process.stderr.write(launcherHelpSection() + "\n");
  let cfg;
  try {
    cfg = resolveConfig({ launcherDir: import.meta.dir });
  } catch (e) {
    process.stderr.write(`autostock: (opencode 도움말 표시 불가 — config 오류: ${(e as Error).message})\n`);
    process.exit(EXIT.OK);
  }
  try {
    // @ts-ignore Bun global
    const proc = Bun.spawn(["bun", "run", "dev", "--", ...consoleArgs], {
      cwd: cfg.consoleCwd,
      env: consoleEnv(cfg, process.env, false),
      stdin: "inherit",
      stdout: "inherit",
      stderr: "inherit",
    });
    const code = await proc.exited;
    process.exit(code === 0 ? EXIT.OK : code);
  } catch (e) {
    process.stderr.write(`autostock: (opencode 도움말 실행 실패: ${(e as Error).message})\n`);
    process.exit(EXIT.OK);
  }
}

export async function main(): Promise<void> {
  // 0. help (F40): short-circuit BEFORE preflight/daemon — `autostock -h` / `--help` prints the
  //    launcher section then forwards the flag to opencode for its full yargs help (loose-fuse).
  //    (supervisor is irrelevant here; --supervisor is already stripped from consoleArgs.)
  const helpArgs = classifyArgs(process.argv.slice(2));
  if (helpArgs.help) await runHelp(helpArgs.consoleArgs);

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
  // F26: `--supervisor` is the ONLY entry to the elevated (whole-codebase read) profile.
  // It requires shell access here (developer-only, FR-4②); the daemon/autonomous paths
  // never pass it. classifyArgs STRIPS it from consoleArgs so it never leaks to opencode's CLI.
  const { supervisor, consoleArgs } = classifyArgs(process.argv.slice(2));
  const env = consoleEnv(cfg, process.env, supervisor);
  if (supervisor) process.stderr.write("autostock: ⚠ SUPERVISOR 모드 (전체 코드 읽기, read-only)\n");
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

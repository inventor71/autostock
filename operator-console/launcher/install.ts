#!/usr/bin/env bun
// F5 launcher — idempotent installer (BR-15, P3). Places ~/.local/bin/autostock shim (Q4=A
// user-level, no sudo), installs+enables the systemd --user unit, and warns if ~/.local/bin
// is not on PATH (no silent mis-install). Re-running is safe.

import { chmodSync, mkdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { deriveRoot, resolveConfig } from "./config";
import { DaemonService } from "./daemon";

export function shimText(autostockRoot: string): string {
  // Bake AUTOSTOCK_ROOT + absolute cli path so the command works from any cwd, like `claude`.
  return `#!/usr/bin/env bash
export AUTOSTOCK_ROOT="${autostockRoot}"
exec bun "${autostockRoot}/operator-console/launcher/cli.ts" "$@"
`;
}

async function main(): Promise<void> {
  const launcherDir = import.meta.dir;
  const autostockRoot = process.env.AUTOSTOCK_ROOT ? process.env.AUTOSTOCK_ROOT : deriveRoot(launcherDir);
  const cfg = resolveConfig({ launcherDir });
  const home = homedir();

  // 1. shim
  const shimPath = cfg.installPath; // ~/.local/bin/autostock
  mkdirSync(dirname(shimPath), { recursive: true });
  writeFileSync(shimPath, shimText(autostockRoot), "utf8");
  chmodSync(shimPath, 0o755);
  console.log(`installed: ${shimPath}`);

  // 2. systemd user unit (install + enable + linger), idempotent.
  const daemon = new DaemonService(cfg);
  await daemon.ensureInstalled();
  console.log(`installed systemd unit: ${daemon.unitPath()} (enabled, linger)`);

  // 3. PATH check — warn loudly if the shim won't be found (no silent mis-install, BR-1 spirit).
  const localBin = join(home, ".local", "bin");
  const onPath = (process.env.PATH ?? "").split(":").includes(localBin);
  if (!onPath) {
    console.warn(
      `\n⚠ ${localBin} is not on PATH. Add it so \`autostock\` is found:\n` +
        `    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc`,
    );
  } else {
    console.log("PATH ok.");
  }

  // 4. Shadow check — another `autostock` earlier in PATH would run INSTEAD of this launcher
  // (e.g. the project's own `autostock` console_script in an active venv/bin). Catch it loudly
  // rather than silently launching the wrong thing (the daemon CLI in paper mode). F5.
  // @ts-ignore Bun global
  const resolved: string | null = Bun.which("autostock");
  if (resolved && resolved !== shimPath) {
    console.warn(
      `\n⚠ another \`autostock\` shadows this launcher and will run instead:\n` +
        `    ${resolved}\n` +
        `  Remove/rename it (e.g. a stale venv console_script) or put ${localBin} earlier in PATH.\n` +
        `  Verify with:  command -v autostock   (should be ${shimPath})`,
    );
  } else if (resolved === shimPath) {
    console.log(`\`autostock\` → ${shimPath}. Run \`autostock\` from anywhere.`);
  }
}

if (import.meta.main) {
  await main();
}

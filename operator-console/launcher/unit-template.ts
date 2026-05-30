// F5 launcher — systemd --user unit text (P3, E3). Q2=A policy: Restart=on-failure + linger.
// critic2 #3/#4: WorkingDirectory is MANDATORY (main.py load_dotenv is CWD-relative); NO
// EnvironmentFile (systemd parser != python-dotenv; the daemon loads .env itself at main.py:366).

export const UNIT_NAME = "autostock-daemon.service";

export interface UnitParams {
  autostockRoot: string;
  python: string; // absolute venv interpreter
  // PATH for the unit. systemd --user does NOT inherit the login-shell PATH, so the daemon's
  // subprocess(['claude', ...]) (src/agent/session.py) fails with FileNotFoundError unless the
  // dir holding `claude` (often an nvm-versioned node bin) is on PATH. DETECTED at install time
  // (DaemonService.resolveDaemonPath), never hardcoded; re-detected on every launcher run so a
  // node-version bump is picked up the next time `autostock` runs. Undefined → omit the line.
  path?: string;
}

export function renderUnit(p: UnitParams): string {
  const pathLine = p.path ? `Environment=PATH=${p.path}\n` : "";
  return `[Unit]
Description=autostock trading daemon (agent + steering)
After=default.target

[Service]
Type=simple
${pathLine}WorkingDirectory=${p.autostockRoot}
ExecStart=${p.python} ${p.autostockRoot}/main.py --mode agent --steering
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
`;
}

/** Candidate venv interpreters, in order; the daemon module picks the first that exists. */
export function pythonCandidates(autostockRoot: string): string[] {
  return [
    `${autostockRoot}/.venv/bin/python`,
    `${autostockRoot}/venv/bin/python`,
    `${autostockRoot}/.venv/bin/python3`,
  ];
}

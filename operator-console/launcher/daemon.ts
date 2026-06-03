// F5 launcher — systemd --user daemon management + health-wait (E3/E4, P2/P3).
// critic #1: health = snapshot `published_at` ADVANCE or 2 consecutive fresh reads, NOT bare
//   mtime, with health_window tuned to the single bus worker's worst-case occupancy (not 5s).
// critic2 #6: published_at is naive-local ISO; parse as LOCAL (new Date(s)) — never assume UTC.
// BR-9.1: `systemctl start` on an already-active unit is an idempotent no-op (not an error).

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { pythonCandidates, renderUnit, UNIT_NAME } from "./unit-template";
import type { LauncherConfig } from "./config";

export const HEALTH_WINDOW_MS = 45_000; // critic #1: bus worst-case, not the 5s publish cadence
export const HEALTHWAIT_TIMEOUT_MS = 60_000; // absorbs cold-start premarket research batch
export const HEALTH_POLL_MS = 1_000;
export const ATTACH_PROBE_MS = 8_000; // attach advance probe: informational only (never gates start)
export const RUN_TIMEOUT_MS = 10_000; // hard cap on a systemctl/loginctl call (review #4: no infinite hang)
// F14: when the unit is `active` but the snapshot isn't fresh, it may just be busy (a long
// LLM turn / slow publish — published_at still advances) OR genuinely wedged (publish frozen
// on a half-open socket). Wait out a long patience window for an advance before declaring a
// wedge, so a healthy-but-slow daemon is never killed; then auto-restart ONCE and re-wait.
export const WEDGE_PATIENCE_MS = 180_000; // active+not-fresh: an advance must appear within this, else wedged
export const RESTART_HEALTH_MS = 180_000; // after an auto-restart, allow a cold-start publish to appear

export interface RunResult {
  code: number;
  stdout: string;
  stderr: string;
}
export type Runner = (args: string[]) => Promise<RunResult>;
export type SnapshotReader = () => Record<string, unknown> | null;

export interface DaemonDeps {
  run?: Runner; // systemctl/loginctl runner
  readSnapshot?: SnapshotReader;
  now?: () => number;
  sleep?: (ms: number) => Promise<void>;
  homeDir?: string;
  fileExists?: (p: string) => boolean;
  writeFile?: (p: string, c: string) => void;
  readFile?: (p: string) => string | null;
  warn?: (msg: string) => void;
  whichClaude?: () => string | null; // absolute path to `claude` on PATH, or null (Bun.which default)
}

/** Default runner: spawn a command, capture stdout/stderr/exit, with a hard timeout (review #4). */
function defaultRunner(timeoutMs = RUN_TIMEOUT_MS): Runner {
  return async (args: string[]): Promise<RunResult> => {
    // @ts-ignore Bun global
    const proc = Bun.spawn(args, { stdout: "pipe", stderr: "pipe" });
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      try {
        proc.kill();
      } catch {
        /* already gone */
      }
    }, timeoutMs);
    try {
      const [stdout, stderr] = await Promise.all([
        new Response(proc.stdout).text(),
        new Response(proc.stderr).text(),
      ]);
      const code = await proc.exited;
      if (timedOut) return { code: 124, stdout: stdout.trim(), stderr: `${args[0]} timed out after ${timeoutMs}ms` };
      return { code, stdout: stdout.trim(), stderr: stderr.trim() };
    } finally {
      clearTimeout(timer);
    }
  };
}

export class DaemonStartError extends Error {}

/** Parse the snapshot's naive-local `published_at` to epoch ms (NaN if absent/bad). */
export function publishedAtMs(snapshot: Record<string, unknown> | null): number {
  if (!snapshot) return NaN;
  const p = snapshot["published_at"];
  if (typeof p !== "string") return NaN;
  return new Date(p).getTime(); // naive-local → local, mirrors sidebar/autostock.tsx:92
}

export interface HealthResult {
  healthy: boolean;
  reason: string;
}

export class DaemonService {
  readonly unitName = UNIT_NAME;
  private run: Runner;
  private readSnapshot: SnapshotReader;
  private now: () => number;
  private sleep: (ms: number) => Promise<void>;
  private home: string;
  private fileExists: (p: string) => boolean;
  private writeFile: (p: string, c: string) => void;
  private readFile: (p: string) => string | null;
  private warn: (msg: string) => void;
  private whichClaude: () => string | null;

  constructor(private cfg: LauncherConfig, deps: DaemonDeps = {}) {
    this.run = deps.run ?? defaultRunner();
    this.readSnapshot = deps.readSnapshot ?? (() => null);
    this.now = deps.now ?? (() => Date.now());
    this.sleep = deps.sleep ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
    this.home = deps.homeDir ?? homedir();
    this.fileExists = deps.fileExists ?? existsSync;
    this.writeFile = deps.writeFile ?? ((p, c) => {
      mkdirSync(dirname(p), { recursive: true });
      writeFileSync(p, c, "utf8");
    });
    this.readFile = deps.readFile ?? ((p) => {
      try {
        return readFileSync(p, "utf8");
      } catch {
        return null;
      }
    });
    this.warn = deps.warn ?? ((m) => console.error(`autostock: warning — ${m}`));
    this.whichClaude = deps.whichClaude ?? (() => {
      // @ts-ignore Bun global — executable-aware (skips dirs/non-exec), unlike a bare existence check.
      return Bun.which("claude");
    });
  }

  unitPath(): string {
    return join(this.home, ".config", "systemd", "user", this.unitName);
  }

  private async sc(args: string[]): Promise<RunResult> {
    return this.run(["systemctl", "--user", ...args]);
  }

  /** systemctl --user is-active → "active" | "inactive" | "failed" | "activating" | "unknown". */
  async state(): Promise<string> {
    const r = await this.sc(["is-active", this.unitName]);
    return (r.stdout || "unknown").trim();
  }

  async isActive(): Promise<boolean> {
    return (await this.state()) === "active";
  }

  /** Pick a Python that can actually run the daemon. Prefer the operator's ACTIVE venv
   *  (VIRTUAL_ENV at install time), then conventional venv dirs — and VALIDATE each can import the
   *  daemon's deps, so a broken/empty `.venv` is skipped instead of being baked into the unit
   *  (which would make the service fail to start). No-silent-failure (BR-1). */
  private async resolvePython(): Promise<string> {
    const venv = process.env.VIRTUAL_ENV;
    const candidates = [
      ...(venv ? [`${venv}/bin/python`] : []),
      ...pythonCandidates(this.cfg.autostockRoot),
    ];
    let firstPresent: string | null = null;
    for (const c of candidates) {
      if (!this.fileExists(c)) continue;
      if (!firstPresent) firstPresent = c;
      const r = await this.run([c, "-c", "import apscheduler, loguru, pydantic"]);
      if (r.code === 0) return c; // imports the daemon deps → good
    }
    // none validated: fall back to the first present interpreter (or python3); health-wait
    // surfaces a real failure loudly rather than silently.
    return firstPresent ?? "python3";
  }

  /** The `Environment=PATH=` value already baked into an on-disk unit, if any. */
  private existingUnitPath(unit: string | null): string | undefined {
    const m = unit?.match(/^Environment=PATH=(.*)$/m);
    return m ? m[1] : undefined;
  }

  /** PATH to bake into the unit. systemd --user starts with a bare PATH that lacks the dir holding
   *  `claude` (often an nvm-versioned node bin), so the daemon's subprocess(['claude', ...]) would
   *  fail with FileNotFoundError. We DETECT `claude` on the launcher's OWN PATH (the operator runs
   *  `autostock` from their login shell, so it resolves there) and prepend its dir to the standard
   *  system dirs. Re-detected every run, so a node-version bump is absorbed on the next `autostock`.
   *
   *  Crucially, if detection FAILS (launcher invoked from a PATH-poor context — cron, another unit,
   *  a non-login shell) we PRESERVE the PATH already in the on-disk unit instead of dropping it:
   *  otherwise self-heal would silently overwrite a working unit with a PATH-less one and re-break
   *  the daemon (critic: HIGH regression). Neither detected nor present → omit + warn loudly. We do
   *  NOT touch the operator's environment (no ~/.local/bin symlinks); only this unit's PATH. */
  private resolveDaemonPath(existingUnit: string | null): string | undefined {
    const std = ["/usr/local/bin", "/usr/bin", "/bin"];
    const claude = this.whichClaude();
    if (claude) {
      const dir = dirname(claude);
      return [dir, ...std.filter((d) => d !== dir)].join(":");
    }
    const existing = this.existingUnitPath(existingUnit);
    if (existing) return existing; // preserve a working unit — never silently regress
    this.warn(
      "`claude` CLI not found on PATH; the daemon unit will have no claude on its PATH and LLM " +
        "turns will fail. Install claude (and ensure it's on your shell PATH), then re-run `autostock`.",
    );
    return undefined;
  }

  /** Install/refresh the unit, reload, enable, enable-linger. Idempotent AND self-healing:
   *  rewrites the unit when its content drifts (review #2 — a stale unit must not silently persist
   *  after a path/template change). linger failure warns rather than silently dropping (review #3). */
  async ensureInstalled(): Promise<void> {
    const path = this.unitPath();
    const existing = this.readFile(path);
    const desired = renderUnit({
      autostockRoot: this.cfg.autostockRoot,
      python: await this.resolvePython(),
      path: this.resolveDaemonPath(existing),
    });
    if (existing !== desired) {
      this.writeFile(path, desired);
      await this.sc(["daemon-reload"]);
    }
    await this.sc(["enable", this.unitName]); // idempotent
    const user = process.env.USER ?? "";
    if (!user) {
      this.warn("$USER 미설정 → linger 생략(부팅 자동시작 비활성). USER를 설정하거나 `loginctl enable-linger`를 수동 실행하세요.");
      return;
    }
    const r = await this.run(["loginctl", "enable-linger", user]);
    if (r.code !== 0) {
      this.warn(`linger 활성화 실패(부팅 자동시작 비활성): ${r.stderr || `loginctl exit ${r.code}`}`);
    }
  }

  /** True if a snapshot is fresh RIGHT NOW — i.e. some daemon (systemd OR manual) is publishing.
   *  The real liveness signal is the snapshot, not systemd state (live-verify finding): a
   *  manually-run daemon is invisible to `systemctl is-active` yet very much alive. */
  isFreshNow(): boolean {
    const pub = publishedAtMs(this.readSnapshot());
    return !Number.isNaN(pub) && this.now() - pub < HEALTH_WINDOW_MS;
  }

  /**
   * Ensure the daemon is up, then attach. Safety rule (review #1 — the dominant constraint):
   * a fresh snapshot ⇒ a daemon is publishing ⇒ **ATTACH, never start.** A live daemon's publish
   * cadence can lag for MINUTES under an LLM turn (premarket research / intraday; APScheduler
   * max_instances=1 starves the 5s snapshot job), so a missing *advance* does NOT mean it's dead.
   * Double-starting a live daemon on the same broker is unacceptable; the lesser evil — attaching
   * to one that died <window ago — is caught by the console's disconnect banner (S6).
   *  - fresh now → attach (advance probe is informational only, never gates a start).
   *  - not fresh → install (idempotent/self-healing) → start (with a re-check race guard) → health-wait.
   *  - unit 'failed' → diagnose (do not paper over with start).
   */
  async ensureRunning(): Promise<HealthResult> {
    if (this.isFreshNow()) {
      // F43: a fresh snapshot means SOME daemon is publishing — but it may be running
      // STALE code (booted before a merge), which silently rejects new console verbs
      // (e.g. F38 `research` → endless "skipping unparseable command line"). The wedge
      // path never catches this (a stale daemon is perfectly healthy). Detect a
      // code-version skew and restart ONCE before attaching. Fail-open (see detectCodeSkew).
      const skew = await this.detectCodeSkew();
      if (skew.stale) return await this.restartForStaleCode(skew.reason);
      const advancing = await this.probeAdvance(ATTACH_PROBE_MS);
      return {
        healthy: true,
        reason: advancing ? "attached (snapshot advancing & fresh)" : "attached (snapshot fresh; publish lagging — busy?)",
      };
    }

    await this.ensureInstalled();
    const st = await this.state();
    if (st === "failed") {
      throw new DaemonStartError(
        `daemon unit is 'failed'. inspect: journalctl --user -u ${this.unitName} -n 50`,
      );
    }
    // F14: unit is `active` but not fresh → busy-or-wedged. Handle in its own path and
    // RETURN, so an auto-restart does NOT fall through to the common healthWait below
    // (that would run a second, redundant health-wait).
    if (st === "active") {
      return await this.handleActiveWedge();
    }
    // not active: race guard + start, then the common (60s) health-wait — unchanged.
    if (this.isFreshNow()) return { healthy: true, reason: "attached (became live before start)" };
    const r = await this.sc(["start", this.unitName]); // idempotent if it raced to active
    if (r.code !== 0 && !/already/i.test(r.stderr)) {
      throw new DaemonStartError(
        `failed to start daemon (systemctl exit ${r.code}). ${r.stderr || ""}`.trim() +
          `\n      → journalctl --user -u ${this.unitName} -n 50`,
      );
    }
    const health = await this.healthWait();
    if (!health.healthy) {
      throw new DaemonStartError(
        `${health.reason} — still starting (premarket research can take minutes) or wedged?\n` +
          `      → journalctl --user -u ${this.unitName} -n 50`,
      );
    }
    return health;
  }

  /** F43: the working-tree HEAD SHA via the injected runner (testable). "" on any failure —
   *  which makes detectCodeSkew fail-OPEN (no restart). Fixed-arg array (no shell): SECURITY-01. */
  async gitHead(): Promise<string> {
    const r = await this.run(["git", "-C", this.cfg.autostockRoot, "rev-parse", "HEAD"]);
    return r.code === 0 ? r.stdout.trim() : "";
  }

  /**
   * F43 version-skew detection: is the publishing daemon running code OLDER than the working tree?
   * Compares the snapshot's stamped `code_version` against the launcher's HEAD. Decision table —
   * biased fail-OPEN so a restart LOOP is impossible:
   *  - launcher HEAD unknown (git failed / not a repo) → NOT stale (G-1: never restart on doubt).
   *  - snapshot has NO `code_version` key → stale (a pre-F43 daemon; ONE restart upgrades it to a
   *    stamping daemon, after which the key is always present — so this fires at most once).
   *  - key present but blank ("") → NOT stale. The daemon IS an F43 daemon that simply couldn't
   *    resolve its own SHA; we can't compare, so we must not restart (else: restart forever).
   *  - SHA present and ≠ HEAD → stale. Equal → not stale.
   */
  async detectCodeSkew(): Promise<{ stale: boolean; reason: string }> {
    const head = await this.gitHead();
    if (!head) return { stale: false, reason: "launcher HEAD unknown — skew check skipped" };
    const snap = this.readSnapshot();
    if (!snap || !("code_version" in snap)) {
      return { stale: true, reason: "daemon predates version stamping (no code_version)" };
    }
    const stamped = typeof snap["code_version"] === "string" ? (snap["code_version"] as string) : "";
    if (!stamped) return { stale: false, reason: "daemon code_version blank (git unresolved) — skew check skipped" };
    if (stamped !== head) {
      return { stale: true, reason: `daemon code ${stamped.slice(0, 7)} ≠ working-tree ${head.slice(0, 7)}` };
    }
    return { stale: false, reason: "code_version matches working tree" };
  }

  /**
   * F43: restart a daemon caught running stale code, then health-wait. Mirrors the wedge path's
   * one-shot `systemctl restart` + RESTART_HEALTH_MS wait. UNCONDITIONAL by design (user decision):
   * no market / in-flight-turn gating — picking up merged code wins over protecting a turn. The new
   * daemon publishes a snapshot stamped with the current SHA, so the next `autostock` run matches
   * and attaches without restarting.
   */
  async restartForStaleCode(reason: string): Promise<HealthResult> {
    this.warn(`daemon running stale code (${reason}) — auto-restarting to load current code`);
    const r = await this.sc(["restart", this.unitName]);
    if (r.code !== 0) {
      throw new DaemonStartError(
        `stale-code auto-restart failed (systemctl exit ${r.code}). ${r.stderr || ""}`.trim() +
          `\n      → journalctl --user -u ${this.unitName} -n 50`,
      );
    }
    const after = await this.healthWait(RESTART_HEALTH_MS);
    if (!after.healthy) {
      throw new DaemonStartError(
        `daemon was running stale code; auto-restarted but snapshot not advancing within ` +
          `${Math.round(RESTART_HEALTH_MS / 1000)}s.\n` +
          `      → journalctl --user -u ${this.unitName} -n 50`,
      );
    }
    return { healthy: true, reason: `auto-restarted (was running stale code: ${reason})` };
  }

  /**
   * F14 self-heal: the unit is `active` but the snapshot isn't fresh. It may be BUSY (a long
   * LLM turn / slow publish — published_at still advances) or genuinely WEDGED (publish frozen).
   * Wait out a long patience window for an advance; a busy daemon is thus never killed. If no
   * advance, restart ONCE and re-wait. We KEEP healthWait's `fresh && advanced` gate (not
   * advance-only): advance-only would risk attaching to a daemon that died moments ago leaving a
   * stale-but-recent snapshot (review #1). Fail-closed: throw rather than falsely attach.
   */
  async handleActiveWedge(): Promise<HealthResult> {
    const busyOrHealthy = await this.healthWait(WEDGE_PATIENCE_MS);
    if (busyOrHealthy.healthy) return busyOrHealthy; // advanced within patience → busy, not wedged
    // wedge confirmed. Race guard: it may have started publishing in the last moment.
    if (this.isFreshNow()) return { healthy: true, reason: "attached (recovered before restart)" };
    const r = await this.sc(["restart", this.unitName]);
    if (r.code !== 0) {
      throw new DaemonStartError(
        `daemon wedged (snapshot frozen) and auto-restart failed (systemctl exit ${r.code}). ` +
          `${r.stderr || ""}`.trim() +
          `\n      → journalctl --user -u ${this.unitName} -n 50`,
      );
    }
    const after = await this.healthWait(RESTART_HEALTH_MS);
    if (!after.healthy) {
      throw new DaemonStartError(
        `daemon was wedged; auto-restarted but snapshot still not advancing within ` +
          `${Math.round(RESTART_HEALTH_MS / 1000)}s.\n` +
          `      → journalctl --user -u ${this.unitName} -n 50`,
      );
    }
    return { healthy: true, reason: "auto-restarted (was wedged); snapshot advancing again" };
  }

  /** Did published_at advance (while staying fresh) within the timeout? Informational only — a
   *  false here never triggers a start (review #1). Returns true on the first observed advance. */
  async probeAdvance(timeoutMs: number): Promise<boolean> {
    const deadline = this.now() + timeoutMs;
    const initial = publishedAtMs(this.readSnapshot());
    while (this.now() <= deadline) {
      const pub = publishedAtMs(this.readSnapshot());
      if (!Number.isNaN(pub) && (Number.isNaN(initial) || pub > initial)) return true;
      await this.sleep(HEALTH_POLL_MS);
    }
    return false;
  }

  /**
   * Poll snapshot.json until the daemon proves liveness: published_at ADVANCES from the first
   * observation while staying fresh (critic #1). Bare mtime is never trusted; "fresh but frozen"
   * (a daemon that died <window ago, leaving a recent snapshot) is correctly NOT accepted —
   * only a new publish (advance) proves the daemon is alive now.
   */
  async healthWait(timeoutMs: number = HEALTHWAIT_TIMEOUT_MS): Promise<HealthResult> {
    const deadline = this.now() + timeoutMs;
    const initial = publishedAtMs(this.readSnapshot());
    while (this.now() <= deadline) {
      const pub = publishedAtMs(this.readSnapshot());
      const fresh = !Number.isNaN(pub) && this.now() - pub < HEALTH_WINDOW_MS;
      const advanced = !Number.isNaN(pub) && (Number.isNaN(initial) || pub > initial);
      if (fresh && advanced) return { healthy: true, reason: "snapshot advancing & fresh" };
      await this.sleep(HEALTH_POLL_MS);
    }
    return {
      healthy: false,
      reason: `snapshot not advancing within ${Math.round(timeoutMs / 1000)}s (daemon wedged/down?)`,
    };
  }
}

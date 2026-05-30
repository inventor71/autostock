// F5 launcher — systemd --user daemon management + health-wait (E3/E4, P2/P3).
// critic #1: health = snapshot `published_at` ADVANCE or 2 consecutive fresh reads, NOT bare
//   mtime, with health_window tuned to the single bus worker's worst-case occupancy (not 5s).
// critic2 #6: published_at is naive-local ISO; parse as LOCAL (new Date(s)) — never assume UTC.
// BR-9.1: `systemctl start` on an already-active unit is an idempotent no-op (not an error).

import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { pythonCandidates, renderUnit, UNIT_NAME } from "./unit-template";
import type { LauncherConfig } from "./config";

export const HEALTH_WINDOW_MS = 45_000; // critic #1: bus worst-case, not the 5s publish cadence
export const HEALTHWAIT_TIMEOUT_MS = 60_000; // absorbs cold-start premarket research batch
export const HEALTH_POLL_MS = 1_000;

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
}

/** Default runner: spawn a command, capture stdout/stderr/exit. */
function defaultRunner(): Runner {
  return async (args: string[]): Promise<RunResult> => {
    // @ts-ignore Bun global
    const proc = Bun.spawn(args, { stdout: "pipe", stderr: "pipe" });
    const [stdout, stderr] = await Promise.all([
      new Response(proc.stdout).text(),
      new Response(proc.stderr).text(),
    ]);
    const code = await proc.exited;
    return { code, stdout: stdout.trim(), stderr: stderr.trim() };
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

  private resolvePython(): string {
    for (const c of pythonCandidates(this.cfg.autostockRoot)) if (this.fileExists(c)) return c;
    return "python3"; // last resort; ensureInstalled diagnoses if even this is wrong at runtime
  }

  /** Create the unit (if absent), reload, enable, enable-linger. Idempotent. */
  async ensureInstalled(): Promise<void> {
    const path = this.unitPath();
    if (!this.fileExists(path)) {
      const python = this.resolvePython();
      this.writeFile(path, renderUnit({ autostockRoot: this.cfg.autostockRoot, python }));
      await this.sc(["daemon-reload"]);
    }
    await this.sc(["enable", this.unitName]); // idempotent
    await this.run(["loginctl", "enable-linger", process.env.USER ?? ""]).catch(() => undefined);
  }

  /**
   * Ensure the daemon is up and publishing. active → verify health; inactive → start (idempotent,
   * BR-9.1) → health-wait; failed → diagnose (do not paper over with start).
   */
  async ensureRunning(): Promise<HealthResult> {
    await this.ensureInstalled();
    const st = await this.state();
    if (st === "failed") {
      throw new DaemonStartError(
        `daemon unit is 'failed'. inspect: journalctl --user -u ${this.unitName} -n 50`,
      );
    }
    if (st !== "active") {
      const r = await this.sc(["start", this.unitName]); // idempotent if it raced to active
      if (r.code !== 0 && !/already/i.test(r.stderr)) {
        throw new DaemonStartError(
          `failed to start daemon (systemctl exit ${r.code}). ${r.stderr || ""}`.trim() +
            `\n      → journalctl --user -u ${this.unitName} -n 50`,
        );
      }
    }
    const health = await this.healthWait();
    if (!health.healthy) {
      throw new DaemonStartError(
        `${health.reason}\n      → journalctl --user -u ${this.unitName} -n 50`,
      );
    }
    return health;
  }

  /**
   * Poll snapshot.json until the daemon proves liveness: published_at ADVANCES from the first
   * observation OR two consecutive fresh reads (critic #1). Bare mtime is never trusted.
   */
  async healthWait(): Promise<HealthResult> {
    const deadline = this.now() + HEALTHWAIT_TIMEOUT_MS;
    const initial = publishedAtMs(this.readSnapshot());
    let consecutiveFresh = 0;
    while (this.now() <= deadline) {
      const pub = publishedAtMs(this.readSnapshot());
      const fresh = !Number.isNaN(pub) && this.now() - pub < HEALTH_WINDOW_MS;
      const advanced = !Number.isNaN(pub) && (Number.isNaN(initial) || pub > initial);
      if (fresh && advanced) return { healthy: true, reason: "snapshot advanced & fresh" };
      consecutiveFresh = fresh ? consecutiveFresh + 1 : 0;
      if (consecutiveFresh >= 2) return { healthy: true, reason: "snapshot fresh (x2)" };
      await this.sleep(HEALTH_POLL_MS);
    }
    return {
      healthy: false,
      reason: `daemon active but snapshot not advancing within ${Math.round(
        HEALTHWAIT_TIMEOUT_MS / 1000,
      )}s (wedged?)`,
    };
  }
}

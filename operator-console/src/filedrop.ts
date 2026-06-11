// F4 Unit B — file-drop client (BR-B2/B5/B6/B9). Owns token attach + atomic append
// of confirmed commands, torn-safe event tail, and snapshot read. The deterministic
// write path (P-B2): a confirmed CommandDraft is built into a SteeringCommand here
// (token from env, never logged) and appended. The LLM never reaches this code.

import { randomUUID } from "node:crypto";
import { appendFileSync, closeSync, existsSync, mkdirSync, openSync, readFileSync, readSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { type SteeringCommand, type SteeringEvent, TOKEN_ENV, type SteeringVerb } from "./schema";

export class NoTokenError extends Error {}

export class FileDrop {
  readonly commandsFile: string;
  readonly eventsFile: string;
  readonly snapshotFile: string;
  readonly monitorFile: string;
  readonly codebaseFile: string;  // F29
  readonly positionsDir: string;  // F53: workspace/positions/
  readonly screeningDir: string;  // F72: workspace/screening/
  private token: string;

  constructor(steeringDir: string, token?: string) {
    mkdirSync(steeringDir, { recursive: true });
    this.commandsFile = join(steeringDir, "commands.jsonl");
    this.eventsFile = join(steeringDir, "events.jsonl");
    this.snapshotFile = join(steeringDir, "snapshot.json");
    this.monitorFile = join(steeringDir, "monitor.json"); // F6: deep-monitoring read view
    this.codebaseFile = join(steeringDir, "codebase.json"); // F29: project tree
    this.positionsDir = join(steeringDir, "..", "workspace", "positions"); // F53
    this.screeningDir = join(steeringDir, "..", "workspace", "screening"); // F72
    this.token = token ?? process.env[TOKEN_ENV] ?? "";
  }

  hasToken(): boolean {
    return this.token.length > 0;
  }

  /** Build a confirmed SteeringCommand. Throws if no token (write disabled, BR-B2). */
  build(verb: SteeringVerb, args: Record<string, unknown>): SteeringCommand {
    if (!this.token) throw new NoTokenError("operator token missing; write disabled");
    return {
      id: randomUUID().replace(/-/g, ""), // uuid4 hex, matches Unit A _new_id()
      ts: new Date().toISOString(),
      verb,
      args,
      confirmed: true, // only confirmed commands reach the channel (Q2=A)
      token: this.token,
      source: "human",
    };
  }

  /** Atomic-enough append: single O_APPEND write of a newline-terminated line.
   * Unit A's torn-line reader + id-dedup absorb any partial/edge case (BR-11). */
  append(cmd: SteeringCommand): void {
    appendFileSync(this.commandsFile, JSON.stringify(cmd) + "\n", { encoding: "utf8" });
  }

  /** Build + append in one step (the confirmed-write path). Returns the command id. */
  send(verb: SteeringVerb, args: Record<string, unknown>): string {
    const cmd = this.build(verb, args);
    this.append(cmd);
    return cmd.id;
  }

  /** Torn-safe read of new events from a byte offset; returns events + new offset
   * (only consumes up to the last newline). Mirrors Unit A jsonl.read_complete_lines. */
  readEvents(offset: number): { events: SteeringEvent[]; offset: number } {
    let size = 0;
    try {
      size = statSync(this.eventsFile).size;
    } catch {
      return { events: [], offset: 0 };
    }
    // review #4: truncation/rotation resets to 0 (cold-start fallback). events.jsonl is
    // append-only (Unit A never rotates it), so this is rare; the consumer dedups by event id.
    if (offset > size) offset = 0;
    if (offset >= size) return { events: [], offset };
    // review #6: read ONLY [offset, size) via a positioned read, not the whole file each poll.
    const len = size - offset;
    const buf = Buffer.allocUnsafe(len);
    const fd = openSync(this.eventsFile, "r");
    let n = 0;
    try {
      n = readSync(fd, buf, 0, len, offset);
    } finally {
      closeSync(fd);
    }
    const chunk = buf.subarray(0, n);
    const lastNl = chunk.lastIndexOf(0x0a);
    if (lastNl === -1) return { events: [], offset }; // no complete line yet
    const complete = chunk.subarray(0, lastNl + 1).toString("utf8");
    const events: SteeringEvent[] = [];
    for (const line of complete.split("\n")) {
      const t = line.trim();
      if (!t) continue;
      try {
        events.push(JSON.parse(t) as SteeringEvent);
      } catch {
        /* skip a malformed line, like Unit A */
      }
    }
    return { events, offset: offset + lastNl + 1 };
  }

  /** Read the live snapshot view (null if absent/torn). */
  readSnapshot(): Record<string, unknown> | null {
    try {
      return JSON.parse(readFileSync(this.snapshotFile, "utf8"));
    } catch {
      return null;
    }
  }

  /** Read the deep-monitoring view (turns/decisions/log) — null if absent/torn. */
  readMonitor(): Record<string, unknown> | null {
    try {
      return JSON.parse(readFileSync(this.monitorFile, "utf8"));
    } catch {
      return null;
    }
  }

  /** F29: Read the project directory tree (published by the daemon at startup). */
  readCodebase(): Record<string, unknown> | null {
    try {
      return JSON.parse(readFileSync(this.codebaseFile, "utf8"));
    } catch {
      return null;
    }
  }

  /** F53: Read a position thesis file (workspace/positions/<SYMBOL>.md).
   *  Returns the markdown content as a string, or null if the file does not exist. */
  readThesis(symbol: string): string | null {
    try {
      const path = join(this.positionsDir, `${symbol.toUpperCase()}.md`);
      if (!existsSync(path)) return null;
      return readFileSync(path, "utf8");
    } catch {
      return null; // fail-closed (SECURITY-15): permission errors etc.
    }
  }

  /** F53: List all symbols that have a thesis file in workspace/positions/.
   *  Returns symbols sorted alphabetically, or an empty array if the directory
   *  is missing or unreadable (fail-closed, SECURITY-15). */
  listTheses(): string[] {
    try {
      if (!existsSync(this.positionsDir)) return [];
      return readdirSync(this.positionsDir)
        .filter((f) => f.endsWith(".md"))
        .map((f) => f.slice(0, -3)) // strip ".md"
        .sort();
    } catch {
      return []; // fail-closed: permission errors etc.
    }
  }

  /** F72: Latest ET date with screening data (scan snapshot or verdicts), or
   *  null when workspace/screening/ is missing/empty/unreadable (fail-closed). */
  latestScreeningDate(): string | null {
    try {
      if (!existsSync(this.screeningDir)) return null;
      const dates = readdirSync(this.screeningDir)
        .map((f) => /^(\d{4}-\d{2}-\d{2})\.(?:scan\.json|verdicts\.jsonl)$/.exec(f)?.[1])
        .filter((d): d is string => d !== undefined)
        .sort();
      return dates.length > 0 ? dates[dates.length - 1] : null;
    } catch {
      return null;
    }
  }

  /** F72: Read one ET date's screening funnel. Returns null when NEITHER file
   *  exists for the date. `scan` is null when absent or unreadable
   *  (`scanUnreadable` distinguishes the two); verdict lines are parsed
   *  leniently — torn/corrupt lines are skipped, the rest kept. */
  readScreening(date: string): {
    scan: Record<string, unknown> | null;
    scanUnreadable: boolean;
    verdicts: Array<Record<string, unknown>>;
  } | null {
    try {
      const scanFile = join(this.screeningDir, `${date}.scan.json`);
      const verdictsFile = join(this.screeningDir, `${date}.verdicts.jsonl`);
      const hasScan = existsSync(scanFile);
      const hasVerdicts = existsSync(verdictsFile);
      if (!hasScan && !hasVerdicts) return null;
      let scan: Record<string, unknown> | null = null;
      if (hasScan) {
        try {
          scan = JSON.parse(readFileSync(scanFile, "utf8"));
        } catch {
          scan = null;
        }
      }
      const verdicts: Array<Record<string, unknown>> = [];
      if (hasVerdicts) {
        try {
          for (const line of readFileSync(verdictsFile, "utf8").split("\n")) {
            const t = line.trim();
            if (!t) continue;
            try {
              const rec = JSON.parse(t);
              if (rec && typeof rec === "object" && !Array.isArray(rec)) verdicts.push(rec);
            } catch {
              /* skip a torn/corrupt line — the journal is evidence, not schema */
            }
          }
        } catch {
          /* unreadable verdicts file → show what we have */
        }
      }
      return { scan, scanUnreadable: hasScan && scan === null, verdicts };
    } catch {
      return null; // fail-closed (SECURITY-15)
    }
  }
}

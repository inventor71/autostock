// F4 Unit B — file-drop client (BR-B2/B5/B6/B9). Owns token attach + atomic append
// of confirmed commands, torn-safe event tail, and snapshot read. The deterministic
// write path (P-B2): a confirmed CommandDraft is built into a SteeringCommand here
// (token from env, never logged) and appended. The LLM never reaches this code.

import { randomUUID } from "node:crypto";
import { appendFileSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { type SteeringCommand, type SteeringEvent, TOKEN_ENV, type SteeringVerb } from "./schema";

export class NoTokenError extends Error {}

export class FileDrop {
  readonly commandsFile: string;
  readonly eventsFile: string;
  readonly snapshotFile: string;
  private token: string;

  constructor(steeringDir: string, token?: string) {
    mkdirSync(steeringDir, { recursive: true });
    this.commandsFile = join(steeringDir, "commands.jsonl");
    this.eventsFile = join(steeringDir, "events.jsonl");
    this.snapshotFile = join(steeringDir, "snapshot.json");
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
    if (offset > size) offset = 0; // truncated/rotated
    if (offset === size) return { events: [], offset };
    const buf = readFileSync(this.eventsFile);
    const slice = buf.subarray(offset);
    const lastNl = slice.lastIndexOf(0x0a);
    if (lastNl === -1) return { events: [], offset }; // no complete line yet
    const complete = slice.subarray(0, lastNl + 1).toString("utf8");
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
}

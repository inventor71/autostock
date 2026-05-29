// F4 Unit B — the interactive confirm/dispatch state machine (BR-B1), SHARED by the
// console stub AND the real opencode TuiPlugin (review #5). Keeping it here (not in
// the stub) means the production console and the PTY e2e exercise the SAME logic, so
// the safety rules (destructive needs CONFIRM, cancel = no-op, error resets pending,
// reads never write) can't drift between the stub and what ships. The LLM never
// reaches this — it only feeds reduced command lines / drafts.

import type { FileDrop } from "./filedrop";
import { ParseError, parseCommand } from "./parser";
import type { SteeringVerb } from "./schema";

export interface DispatchIO {
  write(s: string): void;
}

export type DispatchOutcome =
  | { kind: "read"; verb: string }
  | { kind: "sent"; verb: SteeringVerb; id: string }
  | { kind: "await_confirm"; verb: SteeringVerb; destructive: boolean }
  | { kind: "cancelled" }
  | { kind: "error"; message: string };

export class Dispatcher {
  private pending: { verb: SteeringVerb; args: Record<string, unknown>; destructive: boolean } | null = null;

  constructor(private fd: FileDrop, private io: DispatchIO) {}

  awaitingConfirm(): boolean {
    return this.pending !== null;
  }

  /** Feed one input line; returns a structured outcome (also rendered to io). */
  handle(line: string): DispatchOutcome {
    const text = line.trim();
    try {
      if (this.pending) {
        const p = this.pending;
        this.pending = null; // a confirm prompt consumes exactly the next line
        const accept = p.destructive ? text === "CONFIRM" : /^y(es)?$/i.test(text);
        if (!accept) {
          this.io.write("cancelled (no-op)\n");
          return { kind: "cancelled" };
        }
        const id = this.fd.send(p.verb, p.args);
        this.io.write(`OK ${p.verb} ${id}\n`);
        return { kind: "sent", verb: p.verb, id };
      }
      if (!text) return { kind: "cancelled" };
      const d = parseCommand(text);
      if (d.readOnly) {
        const snap = this.fd.readSnapshot();
        this.io.write(`read ${d.verb}: ${snap ? JSON.stringify(snap).slice(0, 100) : "(no snapshot)"}\n`);
        return { kind: "read", verb: d.verb };
      }
      if (!d.confirmRequired) {
        const id = this.fd.send(d.verb, d.args); // note/context: applies without confirm
        this.io.write(`OK ${d.verb} ${id}\n`);
        return { kind: "sent", verb: d.verb, id };
      }
      this.pending = { verb: d.verb, args: d.args, destructive: d.destructive };
      this.io.write(`Interpreted: ${d.echo} — confirm? [${d.destructive ? "type CONFIRM" : "y/N"}] `);
      return { kind: "await_confirm", verb: d.verb, destructive: d.destructive };
    } catch (e) {
      this.pending = null; // fail-closed: an error never leaves a stale pending
      const message = e instanceof ParseError ? e.message : String(e);
      this.io.write(`error: ${message}\n`);
      return { kind: "error", message };
    }
  }
}

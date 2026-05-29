// F4 Unit B — interactive console STUB (stand-in for the eventual opencode TuiPlugin).
// It wires the SAME parser + filedrop + confirm flow (BR-B1) over a plain readline
// loop, so the PTY injection harness can verify the interactive path end-to-end
// (parse → confirm → token+append) WITHOUT the full opencode TUI. The real TuiPlugin
// reuses src/parser + src/filedrop verbatim; this stub exercises that contract.
//
// Usage: bun run src/console-stub.ts <steering-dir>   (token from STEERING_OPERATOR_TOKEN)

import { createInterface } from "node:readline";
import { FileDrop } from "./filedrop";
import { ParseError, parseCommand } from "./parser";

const dir = process.argv[2] ?? process.env.STEERING_DIR ?? "./steering";
const fd = new FileDrop(dir); // token from env (write disabled if absent)

function w(s: string): void {
  process.stdout.write(s);
}
w(`autostock-console (stub)  token:${fd.hasToken() ? "ok" : "MISSING"}\n> `);

let pending: { verb: ReturnType<typeof parseCommand>["verb"]; args: Record<string, unknown>; destructive: boolean } | null = null;

const rl = createInterface({ input: process.stdin });
rl.on("line", (raw) => {
  const line = raw.trim();
  try {
    if (pending) {
      const accept = pending.destructive ? line === "CONFIRM" : /^y(es)?$/i.test(line);
      if (accept) {
        const id = fd.send(pending.verb, pending.args);
        w(`OK ${pending.verb} ${id}\n`);
      } else {
        w("cancelled (no-op)\n");
      }
      pending = null;
    } else if (line === "quit" || line === "/quit") {
      rl.close();
      return;
    } else if (line) {
      const d = parseCommand(line);
      if (d.readOnly) {
        const snap = fd.readSnapshot();
        w(`read ${d.verb}: ${snap ? JSON.stringify(snap).slice(0, 100) : "(no snapshot)"}\n`);
      } else if (!d.confirmRequired) {
        const id = fd.send(d.verb, d.args); // note/context: applies without confirm
        w(`OK ${d.verb} ${id}\n`);
      } else {
        pending = { verb: d.verb, args: d.args, destructive: d.destructive };
        w(`Interpreted: ${d.echo} — confirm? [${d.destructive ? "type CONFIRM" : "y/N"}] `);
        return; // wait for the confirm line; no prompt redraw
      }
    }
  } catch (e) {
    w(`error: ${e instanceof ParseError ? e.message : String(e)}\n`);
    pending = null;
  }
  w("> ");
});
rl.on("close", () => process.exit(0));

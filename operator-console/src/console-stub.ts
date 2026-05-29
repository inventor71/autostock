// F4 Unit B — interactive console STUB (stand-in for the eventual opencode TuiPlugin).
// It is now a THIN shell over the shared Dispatcher (src/dispatch.ts): readline →
// dispatcher.handle(). The real TuiPlugin will reuse the SAME Dispatcher + parser +
// filedrop, so the PTY injection harness verifies the shipped confirm logic, not a
// stub-only copy (review #5).
//
// Usage: bun run src/console-stub.ts <steering-dir>   (token from STEERING_OPERATOR_TOKEN)

import { createInterface } from "node:readline";
import { Dispatcher } from "./dispatch";
import { FileDrop } from "./filedrop";

const dir = process.argv[2] ?? process.env.STEERING_DIR ?? "./steering";
const fd = new FileDrop(dir); // token from env (write disabled if absent)
const io = { write: (s: string) => process.stdout.write(s) };
const dispatcher = new Dispatcher(fd, io);

io.write(`autostock-console (stub)  token:${fd.hasToken() ? "ok" : "MISSING"}\n> `);

const rl = createInterface({ input: process.stdin });
rl.on("line", (raw) => {
  const line = raw.trim();
  if (!dispatcher.awaitingConfirm() && (line === "quit" || line === "/quit")) {
    rl.close();
    return;
  }
  dispatcher.handle(line);
  if (!dispatcher.awaitingConfirm()) io.write("> "); // no redraw while awaiting a confirm answer
});
rl.on("close", () => process.exit(0));

// F4 Unit B — opencode plugin contributing the `steer` tool (Phase 1 wiring).
//
// This is the NL path: the model proposes `steer({command})`; the tool parses it
// DETERMINISTICALLY (src/parser, the same code the deterministic keystroke path uses),
// and for any book-/lifecycle-mutating command requires a HUMAN confirm via
// `ctx.ask(...)` — opencode core enforces that prompt, so the model cannot bypass the
// confirm or forge the token (BR-B1/B3). Only on approval does it write a token-attached
// command to the file-drop channel (src/filedrop). Reads return the snapshot, no write.
//
// Verified live (this repo cannot build opencode): load into the opencode fork, run
// `bun dev`, and drive it with test/e2e (PTY injection) — see operator-console/README.md.
//
// Env: STEERING_DIR (repo-root steering/ of the daemon) + STEERING_OPERATOR_TOKEN.
// The dedicated TUI panels + pure-keystroke (LLM-bypass) input intercept are Phase 2
// (TuiPlugin); they reuse this same parser/filedrop and the shared Dispatcher.

import { type Plugin, tool } from "@opencode-ai/plugin";
import { FileDrop } from "./filedrop";
import { ParseError, parseCommand } from "./parser";

export const SteerPlugin: Plugin = async () => {
  const fd = new FileDrop(process.env.STEERING_DIR ?? "./steering");

  return {
    tool: {
      steer: tool({
        description:
          "Steer the autostock trading daemon. Pass the operator's command VERBATIM " +
          "(e.g. '/sell AAPL 50%', '/buy AAPL 1000$', '/pause', '/flatten all', " +
          "'/approve 3'). It is parsed deterministically; mutating commands require the " +
          "human to confirm before anything is written. You only propose — you cannot " +
          "skip the confirm or place an order yourself.",
        args: {
          command: tool.schema
            .string()
            .describe("the operator command line, verbatim, e.g. /sell AAPL 50%"),
        },
        async execute({ command }, ctx) {
          let draft;
          try {
            draft = parseCommand(command);
          } catch (e) {
            return `rejected: ${e instanceof ParseError ? e.message : String(e)}`;
          }

          if (draft.readOnly) {
            const snap = fd.readSnapshot();
            return snap ? `snapshot: ${JSON.stringify(snap)}` : "(no snapshot yet)";
          }
          if (!fd.hasToken()) {
            return "rejected: operator token missing (STEERING_OPERATOR_TOKEN); write disabled";
          }

          if (draft.confirmRequired) {
            // Human confirm, enforced by opencode core (NOT the model). Denial throws.
            try {
              await ctx.ask({
                permission: draft.destructive ? "steer.destructive" : "steer.mutate",
                patterns: [draft.verb],
                always: [],
                metadata: { echo: draft.echo, verb: draft.verb, args: draft.args },
              });
            } catch {
              return "cancelled (no-op)";
            }
          }

          const id = fd.send(draft.verb, draft.args);
          return `OK ${draft.verb} ${id} — ${draft.echo}`;
        },
      }),
    },
  };
};

export default SteerPlugin;

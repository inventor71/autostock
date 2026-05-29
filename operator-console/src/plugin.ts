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

// opencode (current sst/opencode) requires a plugin module to **default-export an
// object** `{ server: Plugin, id? }` — readV1Plugin reads `mod.default` and calls
// `.server(input)` (shared.ts:272 / index.ts:114). A bare function export is NOT
// recognized ("must default export an object with server()") — that was why it
// didn't load. So `SteerPlugin` is the Plugin fn, exported via the default object below.
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
        // HUMAN CONFIRM: enforced by opencode's TOOL-LEVEL permission, NOT inside execute.
        // The earlier inner `ctx.ask({permission:"steer.mutate"})` auto-allowed because
        // opencode's Permission.ask only prompts when a CONFIG RULE with action "ask"
        // matches; with no rule it falls through to allow (permission/index.ts:184-188) —
        // that's why it auto-confirmed. The reliable, LLM-unbypassable gate is the standard
        // mechanism `edit`/`bash`/`write` use: configure `permission: { "steer": "ask" }`
        // in opencode.json. opencode then prompts the human (showing command=...) BEFORE
        // execute runs; deny => execute never runs => no write. So execute here only runs
        // AFTER a human approval. (Always-on, config-independent confirm = the Phase-2
        // keystroke/TuiPlugin path; the daemon RiskManager gate is the final safety either way.)
        async execute({ command }, _ctx) {
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
          const id = fd.send(draft.verb, draft.args);
          return `OK ${draft.verb} ${id} — ${draft.echo}`;
        },
      }),
    },
  };
};

// V1 plugin module shape opencode expects: default-export an object with `server`.
export default { id: "autostock-steer", server: SteerPlugin };

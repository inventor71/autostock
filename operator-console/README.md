# autostock-console (F4 Unit B — operator console)

A trader-rebranded **opencode** (`sst/opencode`, MIT) that lets a human steer the
autostock trading daemon. It talks to the daemon ONLY through the repo-root
`steering/` file-drop channel (commands/events/snapshot) — the contract Unit A owns.
The console (incl. its LLM) has **no order authority**: it proposes, a human confirms,
and the daemon's `RiskManager→Broker` gate is the real boundary.

## How the steering command path works (MCP, auto-gated)
`steer` is delivered as a small **MCP server** (`src/mcp-server.ts`). opencode connects
to it and **auto-gates every MCP tool call** via its permission system
(`session/tools.ts:135` calls `ctx.ask({permission:"autostock:steer"})` before the tool
runs). So the **human confirm is enforced by opencode CORE**, not by our code — we can't
mis-key or accidentally remove it (the failure mode we hit with the earlier plugin self-ask).
The model only proposes `steer({command})`; on deny nothing is written.

## Layout
- `src/schema.ts` — TS mirror of Unit A's E7/E8 contract (Unit A pydantic is authoritative).
- `src/parser.ts` — deterministic command parser (fail-closed).
- `src/filedrop.ts` — token (env) + atomic append + torn-safe event tail + snapshot read.
- `src/steer-handler.ts` — the MCP tool logic (parse + read|write); tested.
- `src/mcp-server.ts` — **the MCP server**: tools `steer` (mutating, opencode permission `ask`)
  + `steer_read` (read-only, `allow`).
- `src/dispatch.ts` + `src/console-stub.ts` — shared confirm/dispatch state machine + a
  readline stand-in, used by the PTY injection e2e (and the Phase-2 keystroke path).
- `test/` — bun unit tests (parser/filedrop/dispatch/steer-handler) + `e2e/` PTY injection.

## Auth (critical)
- Console LLM connects to a **non-Anthropic model (e.g. OpenAI) via opencode `auth login`**.
- 🚫 **Never** use the Claude Pro/Max subscription in opencode — ToS violation, and a ban
  would take down the trading agent (same account). agent=Claude subscription, console=OpenAI.

## Run + verify (needs Bun; deps already installed in operator-console/node_modules)
In the opencode fork's `opencode.json`:
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "autostock": {
      "type": "local",
      "command": ["bun", "run", "<abs>/operator-console/src/mcp-server.ts"],
      "environment": {
        "STEERING_DIR": "<autostock-repo>/steering",
        "STEERING_OPERATOR_TOKEN": "<the daemon's token>"
      }
    }
  },
  "permission": { "autostock:steer": "ask", "autostock:steer_read": "allow" }
}
```
Then `bun dev` → type e.g. `sell AAPL 50%` → the model calls the `steer` MCP tool →
**opencode shows a permission prompt** (auto-gate) → approve → only then is the
confirmed+token command written to `steering/commands.jsonl`. `status` → `steer_read`
(no prompt). If a mutating command writes with NO prompt, the `permission` rule is
missing/mismatched (key is `<server>:<tool>` = `autostock:steer`).

## Automated TUI verification
The PTY harness (`test/e2e/`) drives a real TUI headlessly; point `drive()` at `bun dev`,
inject the NL command + the approval keystroke, then assert `steering/commands.jsonl`.

## Roadmap
- **Phase 1 (done):** deterministic core (parser/filedrop/dispatch) + PTY injection harness +
  `steer`/`steer_read` MCP server (confirm = opencode's core auto-gate).
- **Phase 2:** dedicated TUI panels (positions/orders/pending/event-feed via a TuiPlugin) +
  the pure-keystroke LLM-bypass path (reuses `dispatch.ts`).
- **Phase 3:** compile-time removal of opencode's side-effect tools (`registry.ts`:
  task/bash/edit/write/webfetch) → only steer + reads; rebrand the binary; pin the baseline.
- **Phase 4:** cross-language contract test (golden samples vs Unit A pydantic) + injection e2e vs `bun dev`.

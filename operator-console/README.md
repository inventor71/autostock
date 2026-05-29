# autostock-console (F4 Unit B — operator console)

A trader-rebranded **opencode** (`sst/opencode`, MIT) that lets a human steer the
autostock trading daemon. It talks to the daemon ONLY through the repo-root
`steering/` file-drop channel (commands/events/snapshot) — the same contract the
daemon (Unit A) owns. The console (incl. its LLM) has **no order authority**: it
proposes, a human confirms, and the daemon's `RiskManager→Broker` gate is the real
boundary.

## Layout
- `src/schema.ts` — TS mirror of Unit A's E7/E8 contract (Unit A pydantic is authoritative).
- `src/parser.ts` — deterministic command parser (fail-closed).
- `src/filedrop.ts` — token (env) + atomic append + torn-safe event tail + snapshot read.
- `src/dispatch.ts` — shared confirm/dispatch state machine (stub + real TUI reuse it).
- `src/console-stub.ts` — a readline stand-in used by the PTY injection e2e.
- `src/plugin.ts` — **the opencode plugin**: contributes the `steer` tool. The model
  proposes `steer({command})`; mutating commands require a human confirm via opencode's
  `ctx.ask(...)` (core-enforced — the model can't bypass it); only then is a token-attached
  command written to the channel. Reads return the snapshot.
- `test/` — bun unit tests (parser/filedrop/dispatch, 20) + `e2e/` PTY keystroke-injection.

## Auth (critical)
- Console LLM connects to a **non-Anthropic model (e.g. OpenAI) via opencode `auth login`**.
- 🚫 **Never** use the Claude Pro/Max subscription in opencode — ToS violation, and a ban
  would take down the trading agent (same account). agent=Claude subscription, console=OpenAI.

## Run + verify (needs Bun + build-essential; this dev sandbox lacks `make`, so run on your machine)
1. Get the fork: `git clone --depth 1 https://github.com/sst/opencode` (baseline pin TBD in Phase 3).
2. Make this an opencode plugin (project `opencode.json`). **The `permission` rule is
   REQUIRED** — without it opencode auto-allows the `steer` tool and writes with NO human
   prompt (opencode's `Permission.ask` only prompts when a config rule with action `"ask"`
   matches; no rule ⇒ allow). With it, opencode prompts (showing `command=…`) BEFORE the
   tool runs; deny ⇒ no write. This is the LLM-unbypassable human confirm.
   ```json
   {
     "plugin": ["<abs path>/operator-console/src/plugin.ts"],
     "permission": { "steer": "ask" }
   }
   ```
   The plugin already has `@opencode-ai/plugin` in `operator-console/node_modules` so the
   import resolves; the module must default-export `{ id, server }` (it does).
3. Env (same shell as the daemon, so the token is inherited out-of-band):
   ```sh
   export STEERING_DIR=<autostock-repo>/steering
   export STEERING_OPERATOR_TOKEN=<the daemon's token>   # daemon sets it in its env
   ```
4. `bun dev` → opencode TUI. Type e.g. `sell AAPL 50%` → the model calls `steer` →
   **opencode shows a tool-permission prompt** (`steer command=/sell AAPL 50%`) → approve →
   only then is the confirmed+token command written to `steering/commands.jsonl`.
   (If it writes with NO prompt, the `permission:{steer:"ask"}` rule is missing — see step 2.)

## Automated TUI verification (injection harness)
The PTY harness drives a real TUI headlessly. Point it at `bun dev`:
```sh
# the same harness that verifies the stub also verifies the real console
python3 operator-console/test/e2e/pty_harness.py   # (drive() — see run_inject_e2e.py for the pattern)
```
Inject an NL command + the confirm keystroke, then assert `steering/commands.jsonl` got a
`confirmed:true`, token-bearing command. (Approval keystroke depends on opencode's permission
UI — finalize the exact sequence here when you first run it.)

## Status / roadmap
- **Phase 1 (done):** deterministic core (parser/filedrop/dispatch) + PTY injection harness
  (verified) + the `steer` plugin (NL path, confirm via `ctx.ask`).
- **Phase 2:** dedicated TUI panels (positions/orders/pending/event-feed via TuiPlugin) +
  the pure-keystroke LLM-bypass path + full command coverage.
- **Phase 3:** compile-time removal of side-effect tools (`registry.ts`: task/bash/edit/write/
  webfetch) → only `steer`+reads remain; rebrand the binary; pin the baseline.
- **Phase 4:** cross-language contract test (golden samples vs Unit A pydantic) + run the
  injection e2e against `bun dev`.

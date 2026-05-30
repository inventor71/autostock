# autostock-console (F4 Unit B — operator console)

A trader-rebranded **opencode** (`sst/opencode`, MIT) that lets a human steer the
autostock trading daemon. It talks to the daemon ONLY through the repo-root
`steering/` file-drop channel (commands/events/snapshot) — the contract Unit A owns.
The console (incl. its LLM) has **no order authority**: it proposes, a human confirms,
and the daemon's `RiskManager→Broker` gate is the real boundary.

## Command path: natural language → MCP, auto-gated (single path)
The operator steers in **natural language**. `steer` is delivered as a small **MCP server**
(`src/mcp-server.ts`); opencode connects to it and **auto-gates every MCP tool call** via its
permission system (`session/tools.ts:135` calls `ctx.ask({permission:"autostock_steer"})`
before the tool runs). So the **human confirm is enforced by opencode CORE**, not by our code —
we can't mis-key or accidentally remove it. The model only **proposes** `steer({command})`
(e.g. you say "sell half my AAPL" → it proposes `/sell AAPL 50%`); on deny nothing is written.

Determinism still lives in the path: the proposed command is validated by the deterministic
`parser.ts` (the same parser regardless of how it was phrased) before the confirmed, token-
stamped line is appended to `steering/commands.jsonl`. `steer_read` (status/positions/…) is
read-only (`allow`, no prompt).

### Design note — why one command path (NL-only)
An earlier plan added a SECOND, model-free keystroke command path (a TUI plugin driving the
parser directly). We **removed it** (2026-05-30) in favour of a single NL path, for simplicity:
both paths shared the same confirm + `RiskManager→Broker` gate, so they were equivalent on
safety; the second path only saved typing. Trade-off accepted: steering now depends on the
console LLM (OpenAI) being available — the break-glass for an LLM/API outage is the broker's
own UI (Alpaca), after which the daemon reconciles. The deterministic *parser/validator* is
kept (it's inside the MCP path); only the redundant second UI is gone.

## Layout
- `src/schema.ts` — TS mirror of Unit A's E7/E8 contract (Unit A pydantic is authoritative).
- `src/parser.ts` — deterministic command parser (fail-closed).
- `src/filedrop.ts` — token (env) + atomic append + torn-safe event tail + snapshot read.
- `src/steer-handler.ts` — the MCP tool logic (parse + read|write); tested.
- `src/mcp-server.ts` — **the MCP server**: tools `steer` (mutating, opencode permission `ask`)
  + `steer_read` (read-only, `allow`).
- `test/` — bun unit tests (parser / filedrop / steer-handler).

## Tool lockdown (Phase 3 — defense-in-depth, two layers)
The console must have NO capability beyond reads + the human-confirmed `steer`. Two
independent layers enforce this:
1. **Permission default-deny** (`cli/opencode.json`): `"*": "deny"` + a read-only allowlist
   (`read`/`glob`/`grep`/`lsp`) + `autostock_steer` (`ask`) / `autostock_steer_read` (`allow`).
   Verified against opencode's real permission engine: `bun run verify-lockdown.ts`.
2. **Compile-time removal** (`packages/opencode/src/tool/registry.ts`): under
   `AUTOSTOCK_LOCKDOWN=on` the side-effecting builtins (bash/edit/write/task/webfetch/
   websearch/patch/repo_*) are **never registered**, so they are never offered to the model
   and opencode's tool-permission bugs (#5894/#6396) are structurally moot — not merely
   denied. Only read-only builtins survive; custom MCP tools (steer) are always exposed.
   The launch (`bun dev`) sets `AUTOSTOCK_LOCKDOWN=on` by default. Asserted (absence, id-
   agnostic) in `packages/opencode/test/tool/registry.test.ts`.

## Sidebar
The autostock panel (run-state / market / positions / open-orders / pending / event-feed)
reads `steering/snapshot.json` + tails `steering/events.jsonl` every 1.5s (read-only). Events
render as compact human lines (`HH:MM <glyph> outcome · detail`), not raw JSON, and wrap to
the panel width. Toggle the whole sidebar with `<leader>b`.

Width is fixed at 42 cols upstream; this fork makes it overridable:
`AUTOSTOCK_SIDEBAR_WIDTH=<24..120>` (e.g. set it in `cli/.env` for a roomier event feed).
A proper mouse-drag resize is intentionally deferred to a separate feature.

## Pinned baseline
Hard fork of `sst/opencode` at **v1.15.12** (initial spike commit `0147908`). Re-pin = rebase
our small set of autostock commits (lockdown filter in `registry.ts`, sidebar panel, MCP/config,
verify script) onto a newer upstream tag. Branding is intentionally surface-only (kept minimal)
to keep that re-pin cheap.

## Auth (critical)
- Console LLM connects to a **non-Anthropic model (e.g. OpenAI) via opencode `auth login`**.
- 🚫 **Never** use the Claude Pro/Max subscription in opencode — ToS violation, and a ban
  would take down the trading agent (same account). agent=Claude subscription, console=OpenAI.

## Run + verify (needs Bun; deps already installed in operator-console/node_modules)
The machine/MCP wiring lives in `cli/.opencode/opencode.jsonc` (portable via `{env:}`); the
committed `cli/opencode.json` holds the permission lockdown. MCP server entry:
```json
{
  "mcp": {
    "autostock": {
      "type": "local",
      "command": ["bun", "run", "{env:AUTOSTOCK_ROOT}/operator-console/src/mcp-server.ts"],
      "environment": {
        "STEERING_DIR": "{env:STEERING_DIR}",
        "STEERING_OPERATOR_TOKEN": "{env:STEERING_OPERATOR_TOKEN}"
      }
    }
  }
}
```
Then `bun dev` → say e.g. `sell AAPL 50%` → the model calls the `steer` MCP tool →
**opencode shows a permission prompt** (auto-gate) → approve → only then is the
confirmed+token command written to `steering/commands.jsonl`. `status` → `steer_read`
(no prompt). If a mutating command writes with NO prompt, the `permission` rule is
missing/mismatched — the key is **`<server>_<tool>`** (underscore), i.e. `autostock_steer`
(MCP.tools() keys by `sanitize(client)+"_"+sanitize(name)`, mcp/index.ts:696). NOT a colon.

## Roadmap
- **Phase 1 (done):** deterministic core (`parser`/`filedrop`/`schema`) + `steer`/`steer_read`
  MCP server (confirm = opencode's core auto-gate).
- **Phase 2 (done):** dedicated read-only TUI sidebar (run-state/positions/orders/pending/
  event-feed). NL is the single command path (the once-planned model-free keystroke UI was
  removed — see the design note above).
- **Phase 3 (done):** compile-time removal of opencode's side-effect tools (`registry.ts`,
  `AUTOSTOCK_LOCKDOWN=on`: bash/edit/write/task/webfetch/websearch/patch/repo_*) → only steer +
  reads; absence-asserted in `test/tool/registry.test.ts`; baseline pinned (opencode v1.15.12);
  branding surface-only. (Layered atop the Phase-1 permission default-deny.)
- **Phase 4 (done):** cross-language contract test. The console↔daemon file-drop JSON is the
  only coupling (NL-only), so verb/event-kind/envelope-field drift would silently break it. A
  golden `contract/contract.json` (generated from Unit A's pydantic models) is pinned from BOTH
  sides: `tests/test_steering_contract.py` (live models == golden) and `test/contract.test.ts`
  (schema.ts runtime consts + `FileDrop.build` envelope == golden). Drift on either side fails a
  test. `schema.ts` adds `ALL_VERBS`/`ALL_EVENT_KINDS`/`COMMAND_FIELDS`/`EVENT_FIELDS` with
  compile-time exhaustiveness checks against the types. Regenerate (intentional change):
  `python tests/test_steering_contract.py --write`.

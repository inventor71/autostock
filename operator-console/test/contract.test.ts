// F4 Phase 4 — cross-language steering contract (TS mirror side).
// Pins operator-console's runtime contract surface (schema.ts consts + the actual
// FileDrop envelope) to the golden contract/contract.json generated from Unit A's pydantic
// models. The Python side (tests/test_steering_contract.py) pins the live models to the same
// golden. Together: if a verb/event-kind/envelope-field drifts on EITHER side, a test fails
// before the daemon would silently reject a command. (Per-verb args semantics are covered by
// parser.test.ts + the daemon's command tests; this guards the schema envelope + enums.)
import { describe, expect, test } from "bun:test"
import { mkdtempSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { readFileSync } from "node:fs"
import { ALL_EVENT_KINDS, ALL_VERBS, COMMAND_ARGS, COMMAND_FIELDS, EVENT_FIELDS } from "../src/schema"
import { FileDrop } from "../src/filedrop"

const golden = JSON.parse(
  readFileSync(join(import.meta.dir, "..", "contract", "contract.json"), "utf8"),
) as {
  verbs: string[]
  event_kinds: string[]
  command_fields: string[]
  event_fields: string[]
  command_args: Record<string, string[]>
}

const sorted = (a: readonly string[]) => [...a].sort()

describe("cross-language steering contract (TS mirror vs Unit A pydantic golden)", () => {
  test("verb set matches the authoritative contract", () => {
    expect(sorted(ALL_VERBS)).toEqual(sorted(golden.verbs))
  })

  test("event kinds match", () => {
    expect(sorted(ALL_EVENT_KINDS)).toEqual(sorted(golden.event_kinds))
  })

  test("command envelope fields match", () => {
    expect(sorted(COMMAND_FIELDS)).toEqual(sorted(golden.command_fields))
  })

  test("event envelope fields match", () => {
    expect(sorted(EVENT_FIELDS)).toEqual(sorted(golden.event_fields))
  })

  // F9 (NFR-3): per-verb structured args must match across languages so a renamed/
  // retyped field is caught here, not only at live order time.
  test("per-verb command args match the authoritative contract", () => {
    expect(Object.keys(COMMAND_ARGS).sort()).toEqual(Object.keys(golden.command_args).sort())
    for (const verb of Object.keys(COMMAND_ARGS) as (keyof typeof COMMAND_ARGS)[]) {
      expect(sorted(COMMAND_ARGS[verb])).toEqual(sorted(golden.command_args[verb]))
    }
  })

  test("FileDrop.build emits exactly the contract command envelope", () => {
    const fd = new FileDrop(mkdtempSync(join(tmpdir(), "contract-")), "tok")
    const cmd = fd.build("sell", { symbol: "AAPL", size: 50, unit: "%" })
    expect(sorted(Object.keys(cmd))).toEqual(sorted(golden.command_fields))
    expect(cmd.confirmed).toBe(true) // only confirmed records reach the channel
    expect(cmd.source).toBe("human")
    expect(cmd.token).toBe("tok")
    expect(cmd.verb).toBe("sell")
  })
})

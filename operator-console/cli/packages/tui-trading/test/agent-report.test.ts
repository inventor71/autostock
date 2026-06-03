import { expect, test, describe, beforeAll, afterAll } from "bun:test"
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "fs"
import { tmpdir } from "os"
import { join } from "path"
import { readAgentReport, maskSecrets } from "../src/hooks/use-session-data"

// F41: the turn overlay drills into per-round / per-sub-agent evaluations persisted
// by the daemon at workspace/agent_reports/<turn_id>.json. readAgentReport reads them
// straight from the journal (same direct-file approach as the historical session path),
// so it works for both the live and any past session given (workspace_root, turn_id).

describe("readAgentReport", () => {
  let root: string

  beforeAll(() => {
    root = mkdtempSync(join(tmpdir(), "f41-"))
    mkdirSync(join(root, "agent_reports"), { recursive: true })
    writeFileSync(
      join(root, "agent_reports", "R5.json"),
      JSON.stringify({
        turn_id: "R5",
        et_date: "2026-06-02",
        ts: "2026-06-02T21:42:52+09:00",
        turn_type: "research",
        mode: "sequential",
        n_agents: 2,
        agents: [
          { index: 0, label: "Round 1 · Initial", role: "initial pass", status: "ok", text: "lean HOLD AAPL\nRTX cushion +23%" },
          { index: 1, label: "Round 2 · Debate", role: "debate", status: "ok", text: "concede RTX catalyst failed" },
        ],
        synthesis: { text: "HOLD AAPL, HOLD RTX, SELL TSLA" },
      }),
    )
    // malformed
    writeFileSync(join(root, "agent_reports", "BAD.json"), "{not json")
  })

  afterAll(() => rmSync(root, { recursive: true, force: true }))

  test("reads a persisted report by turn_id", () => {
    const r = readAgentReport(root, "R5")
    expect(r).not.toBeNull()
    expect(r!.mode).toBe("sequential")
    expect(r!.agents).toHaveLength(2)
    expect(r!.agents[0]!.label).toBe("Round 1 · Initial")
    expect(r!.agents[0]!.text).toContain("lean HOLD AAPL")
    expect(r!.synthesis.text).toContain("SELL TSLA")
  })

  test("missing turn → null", () => {
    expect(readAgentReport(root, "R99")).toBeNull()
  })

  test("blank/empty inputs → null", () => {
    expect(readAgentReport(root, "")).toBeNull()
    expect(readAgentReport(root, null)).toBeNull()
    expect(readAgentReport(null, "R5")).toBeNull()
  })

  test("malformed json → null (never throws)", () => {
    expect(readAgentReport(root, "BAD")).toBeNull()
  })

  test("normalizes unknown status to ok and missing fields", () => {
    writeFileSync(
      join(root, "agent_reports", "R6.json"),
      JSON.stringify({ turn_id: "R6", agents: [{ index: 0, status: "weird", text: "x" }] }),
    )
    const r = readAgentReport(root, "R6")
    expect(r!.agents[0]!.status).toBe("ok")
    expect(r!.agents[0]!.label).toBe("Agent 1")
  })
})

describe("maskSecrets", () => {
  test("redacts secret key/value pairs", () => {
    expect(maskSecrets("api_key=abc123def")).toContain("***")
    expect(maskSecrets("token: shhhh")).toContain("***")
  })

  test("redacts long opaque blobs", () => {
    const blob = "A1b2C3d4E5f6G7h8I9j0K1l2M3n4"
    expect(maskSecrets(`value ${blob}`)).toContain("***")
  })

  test("leaves ordinary prose intact", () => {
    expect(maskSecrets("HOLD AAPL, sell TSLA")).toBe("HOLD AAPL, sell TSLA")
  })

  test("empty → empty", () => {
    expect(maskSecrets("")).toBe("")
  })
})

import { expect, test, describe, beforeAll, afterAll } from "bun:test"
import { mkdtempSync, writeFileSync, rmSync } from "fs"
import { tmpdir } from "os"
import { join } from "path"
import { readSessionData, correlateTurnId } from "../src/hooks/use-session-data"
import type { MonitorData } from "../src/types"

// F36: a clicked past-date turn/intervention marker must resolve its detail from the
// SAME selected-date session the timeline rendered — not the live monitor payload.
// These cover the historical decision restore + ts→turn correlation (mirrors the
// daemon's runtime.py `_correlate_turn`).

describe("correlateTurnId", () => {
  // [started_at, turn_id] in chronological file order.
  const idx: Array<[string, string]> = [
    ["2026-06-02T09:35:00-04:00", "W12"],
    ["2026-06-02T10:05:00-04:00", "W13"],
  ]

  test("picks the most recent turn started at or before the decision", () => {
    expect(correlateTurnId("2026-06-02T09:38:00-04:00", idx)).toBe("W12")
    expect(correlateTurnId("2026-06-02T10:07:00-04:00", idx)).toBe("W13")
  })

  test("decision before any turn started → null", () => {
    expect(correlateTurnId("2026-06-02T09:30:00-04:00", idx)).toBeNull()
  })

  test("empty ts or empty index → null", () => {
    expect(correlateTurnId("", idx)).toBeNull()
    expect(correlateTurnId("2026-06-02T10:07:00-04:00", [])).toBeNull()
  })

  test("falls back to lexical compare when a timestamp is unparseable", () => {
    const lex: Array<[string, string]> = [["a", "T1"], ["m", "T2"]]
    expect(correlateTurnId("z", lex)).toBe("T2")
    expect(correlateTurnId("b", lex)).toBe("T1")
  })
})

describe("readSessionData", () => {
  let root: string
  // The selected (past) date; the live session is a different day so we exercise the
  // file-reading historical branch.
  const DAY = "2026-06-02"

  const monitor = (): MonitorData => ({
    ts: "2026-06-03T12:00:00-04:00",
    current_turn: null,
    workspace_root: root,
    session_et_date: "2026-06-03",
    turns: { today_count: 0, today_cost_usd: 0, recent: [] },
    decisions: [],
    interventions: [],
    log: [],
  })

  beforeAll(() => {
    root = mkdtempSync(join(tmpdir(), "f36-session-"))
    const turns = [
      { turn_id: "W12", turn_type: "intraday", started_at: "2026-06-02T09:35:00-04:00", ts: "2026-06-02T09:40:00-04:00", et_date: DAY, num_decisions: 1, cost_usd: 0.2 },
      { turn_id: "W13", turn_type: "intraday", started_at: "2026-06-02T10:05:00-04:00", ts: "2026-06-02T10:10:00-04:00", et_date: DAY, num_decisions: 1, cost_usd: 0.3 },
      { turn_id: "W01", turn_type: "research", started_at: "2026-06-01T09:35:00-04:00", ts: "2026-06-01T09:40:00-04:00", et_date: "2026-06-01", num_decisions: 0, cost_usd: 0.1 },
    ]
    // decisions.jsonl carries NO turn_id / et_date — both reconstructed from ts.
    const decisions = [
      { ts: "2026-06-02T09:38:00-04:00", symbol: "AAPL", action: "buy", confidence: 0.8, reason: "breakout", source: "agent" },
      { ts: "2026-06-02T10:07:00-04:00", symbol: "META", action: "sell", reason: "stop", source: "agent" },
      { ts: "2026-06-02T09:30:00-04:00", symbol: "TSLA", action: "hold", reason: "pre-open", source: "agent" },
      { ts: "2026-06-01T11:00:00-04:00", symbol: "NVDA", action: "buy", reason: "other day", source: "agent" },
    ]
    const directives = [
      { ts: "2026-06-02T11:00:00-04:00", command: "sell", args: { symbol: "AAPL" }, et_date: DAY, outcome: "ok" },
    ]
    writeFileSync(join(root, "turns.jsonl"), turns.map((t) => JSON.stringify(t)).join("\n") + "\n")
    writeFileSync(join(root, "decisions.jsonl"), decisions.map((d) => JSON.stringify(d)).join("\n") + "\n")
    writeFileSync(join(root, "human_directives.jsonl"), directives.map((d) => JSON.stringify(d)).join("\n") + "\n")
  })

  afterAll(() => rmSync(root, { recursive: true, force: true }))

  test("filters turns by the selected ET date", () => {
    const s = readSessionData(monitor(), DAY)
    expect(s.turns.map((t) => t.id)).toEqual(["W12", "W13"])
  })

  test("restores decisions for the date and correlates each to its turn", () => {
    const s = readSessionData(monitor(), DAY)
    // NVDA (2026-06-01) excluded by et_date; the other 3 kept.
    expect(s.decisions.map((d) => d.symbol)).toEqual(["AAPL", "META", "TSLA"])
    const bySym = Object.fromEntries(s.decisions.map((d) => [d.symbol, d]))
    expect(bySym.AAPL!.turn_id).toBe("W12")
    expect(bySym.META!.turn_id).toBe("W13")
    expect(bySym.TSLA!.turn_id).toBeNull() // 09:30 is before W12 started (09:35)
  })

  test("normalizes action + confidence, defaults source", () => {
    const s = readSessionData(monitor(), DAY)
    const bySym = Object.fromEntries(s.decisions.map((d) => [d.symbol, d]))
    expect(bySym.AAPL!.action).toBe("BUY")
    expect(bySym.AAPL!.confidence).toBe(0.8)
    expect(bySym.META!.confidence).toBeNull()
  })

  test("overlay's per-turn decision filter matches the historical turn id", () => {
    const s = readSessionData(monitor(), DAY)
    expect(s.decisions.filter((d) => d.turn_id === "W13").map((d) => d.symbol)).toEqual(["META"])
  })

  test("live session returns the monitor payload's decisions unchanged", () => {
    const m = monitor()
    m.decisions = [{ turn_id: "L1", ts: "09:40", symbol: "SPY", action: "BUY", confidence: null, reason: "x", source: "agent" }]
    const s = readSessionData(m, "2026-06-03")
    expect(s.decisions).toBe(m.decisions)
  })
})

import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import fc from "fast-check";
import { z } from "zod";
import { afterAll, describe, expect, it } from "vitest";

import { readFileStable, readJsonFile, tailJsonl } from "@/server/safe-read";

const tmp = mkdtempSync(path.join(os.tmpdir(), "viz-safe-read-"));
afterAll(() => rmSync(tmp, { recursive: true, force: true }));

const RecordSchema = z.looseObject({ ts: z.string(), v: z.number() });

let fileNo = 0;
function tmpFile(content?: string): string {
  const p = path.join(tmp, `f${fileNo++}`);
  if (content !== undefined) writeFileSync(p, content);
  return p;
}

describe("readJsonFile (L2a)", () => {
  it("parses a valid JSON file", async () => {
    const p = tmpFile(JSON.stringify({ ts: "2026-06-13", v: 1, extra: "kept" }));
    const out = await readJsonFile(p, RecordSchema);
    expect(out).not.toBeNull();
    expect(out!.v).toBe(1);
    expect((out as Record<string, unknown>).extra).toBe("kept"); // passthrough
  });

  it("returns null when the file is missing (fail-honest)", async () => {
    expect(await readJsonFile(path.join(tmp, "nope.json"), RecordSchema)).toBeNull();
  });

  it("returns null on invalid JSON without throwing", async () => {
    expect(await readJsonFile(tmpFile("{truncated"), RecordSchema)).toBeNull();
  });

  it("returns null on schema mismatch (drift signal)", async () => {
    expect(await readJsonFile(tmpFile(JSON.stringify({ v: "NaN" })), RecordSchema)).toBeNull();
  });
});

describe("tailJsonl (L2b)", () => {
  const line = (v: number) => JSON.stringify({ ts: "t", v });

  it("parses complete newline-terminated lines", async () => {
    const p = tmpFile(`${line(1)}\n${line(2)}\n`);
    const out = await tailJsonl(p, RecordSchema);
    expect(out.map((r) => r.v)).toEqual([1, 2]);
  });

  it("discards a torn (unterminated) final line", async () => {
    const p = tmpFile(`${line(1)}\n{"ts":"t","v":2`);
    const out = await tailJsonl(p, RecordSchema);
    expect(out.map((r) => r.v)).toEqual([1]);
  });

  it("skips unparsable interior lines and keeps the rest", async () => {
    const p = tmpFile(`${line(1)}\nnot-json\n${line(3)}\n`);
    const out = await tailJsonl(p, RecordSchema);
    expect(out.map((r) => r.v)).toEqual([1, 3]);
  });

  it("returns [] for a missing file", async () => {
    expect(await tailJsonl(path.join(tmp, "missing.jsonl"), RecordSchema)).toEqual([]);
  });

  it("respects maxLines (keeps the newest)", async () => {
    const p = tmpFile([1, 2, 3, 4, 5].map(line).join("\n") + "\n");
    const out = await tailJsonl(p, RecordSchema, { maxLines: 2 });
    expect(out.map((r) => r.v)).toEqual([4, 5]);
  });

  it("PBT: never throws and yields only schema-valid records for arbitrary truncations", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(
          fc.oneof(
            fc.integer().map((v) => line(v)),
            fc.string().filter((s) => !s.includes("\n")), // junk lines
          ),
          { maxLength: 20 },
        ),
        fc.nat(),
        async (lines, cutSeed) => {
          const full = lines.map((l) => `${l}\n`).join("");
          const cut = full.length === 0 ? 0 : cutSeed % (full.length + 1);
          const p = tmpFile(full.slice(0, cut)); // arbitrary byte truncation
          const out = await tailJsonl(p, RecordSchema);
          for (const rec of out) expect(() => RecordSchema.parse(rec)).not.toThrow();
        },
      ),
      { numRuns: 50 },
    );
  });
});

describe("readFileStable (L2c)", () => {
  it("returns content with stale:false for a quiet file (multibyte-safe)", async () => {
    const p = tmpFile("한국어 thesis 본문 — multibyte bytes ≠ chars");
    const out = await readFileStable(p);
    expect(out).not.toBeNull();
    expect(out!.stale).toBe(false);
    expect(out!.content).toContain("thesis");
  });

  it("returns null for a missing file", async () => {
    expect(await readFileStable(path.join(tmp, "gone.md"))).toBeNull();
  });
});

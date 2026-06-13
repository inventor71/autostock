import path from "node:path";
import { promises as fs } from "node:fs";
import { z } from "zod";

import { router, publicProcedure } from "@/server/trpc";
import { equityPath, positionsDir, snapshotPath } from "@/server/paths";
import { readFileStable, readJsonFile, tailJsonl } from "@/server/safe-read";
import {
  EquityRecordSchema,
  SnapshotSchema,
  type ThesisDoc,
} from "@/server/schemas";

/** BR-7: symbols look like "RTX", "BRK.B", "GOOGL" — nothing path-like. */
export const SYMBOL_RE = /^[A-Z][A-Z0-9.\-]{0,9}$/;

const THESIS_FILE_RE = /^([A-Z][A-Z0-9.\-]{0,9})\.md$/;

async function listPositionSymbols(): Promise<string[]> {
  let entries: string[];
  try {
    entries = await fs.readdir(positionsDir());
  } catch {
    return []; // missing dir = no theses yet (fail-honest)
  }
  return entries
    .map((name) => THESIS_FILE_RE.exec(name)?.[1])
    .filter((s): s is string => s !== undefined)
    .sort();
}

export const portfolioRouter = router({
  /** Live daemon snapshot, or null when absent/unparsable (BR-8). */
  snapshot: publicProcedure.query(() => readJsonFile(snapshotPath(), SnapshotSchema)),

  /** Equity curve records within the window, oldest → newest. */
  equity: publicProcedure
    .input(
      z
        .object({ sinceDays: z.number().int().min(1).max(365).default(30) })
        .default({ sinceDays: 30 }),
    )
    .query(async ({ input }) => {
      const records = await tailJsonl(equityPath(), EquityRecordSchema, {
        maxLines: 1000,
      });
      const cutoffMs = Date.now() - input.sinceDays * 86_400_000;
      return records.filter((r) => {
        const t = Date.parse(r.ts);
        return Number.isNaN(t) ? false : t >= cutoffMs;
      });
    }),

  /** Symbols that have a thesis doc on disk. */
  listPositions: publicProcedure.query(() => listPositionSymbols()),

  /**
   * Opaque thesis markdown for one symbol. Input is validated by regex AND
   * checked against the actual directory listing (double whitelist, BR-7) —
   * the symbol never becomes a path without passing both.
   */
  thesis: publicProcedure
    .input(z.object({ symbol: z.string().regex(SYMBOL_RE) }))
    .query(async ({ input }): Promise<ThesisDoc | null> => {
      const symbols = await listPositionSymbols();
      if (!symbols.includes(input.symbol)) return null;
      const read = await readFileStable(
        path.join(positionsDir(), `${input.symbol}.md`),
      );
      if (read === null) return null;
      return {
        symbol: input.symbol,
        markdown: read.content,
        mtimeMs: read.mtimeMs,
        stale: read.stale,
      };
    }),
});

import path from "node:path";
import { promises as fs } from "node:fs";
import { z } from "zod";

import { router, publicProcedure } from "@/server/trpc";
import {
  decisionsPath,
  equityPath,
  healthPath,
  positionsDir,
  qualityDir,
  regimePath,
  snapshotPath,
  tradesPath,
  turnsPath,
  watchlistPath,
} from "@/server/paths";
import { readFileStable, readJsonFile, tailJsonl } from "@/server/safe-read";
import {
  DecisionSchema,
  EquityRecordSchema,
  HealthSchema,
  QualitySchema,
  SnapshotSchema,
  TradeSchema,
  TurnSchema,
  type MarkdownDoc,
  type ThesisDoc,
} from "@/server/schemas";

/** YYYY-MM-DD.json — guards the quality-dir listing against unexpected names. */
const QUALITY_FILE_RE = /^(\d{4}-\d{2}-\d{2})\.json$/;

async function latestQualityFile(): Promise<{ date: string; path: string } | null> {
  let entries: string[];
  try {
    entries = await fs.readdir(qualityDir());
  } catch {
    return null; // missing dir — no metrics yet (fail-honest)
  }
  const dates = entries
    .map((name) => QUALITY_FILE_RE.exec(name)?.[1])
    .filter((d): d is string => d !== undefined)
    .sort();
  const date = dates.at(-1);
  if (date === undefined) return null;
  return { date, path: path.join(qualityDir(), `${date}.json`) };
}

async function readMarkdownDoc(absPath: string): Promise<MarkdownDoc | null> {
  const read = await readFileStable(absPath);
  if (read === null) return null;
  return { markdown: read.content, mtimeMs: read.mtimeMs, stale: read.stale };
}

/** Shared "recent N rows" input for jsonl tail procedures. */
const limitInput = z
  .object({ limit: z.number().int().min(1).max(500).default(50) })
  .default({ limit: 50 });

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

  /** Recent agent decisions (newest last on disk), tail-read for the window. */
  decisions: publicProcedure
    .input(limitInput)
    .query(({ input }) => tailJsonl(decisionsPath(), DecisionSchema, { maxLines: input.limit })),

  /** Recent agent turns (cost/tokens/summary), tail-read. */
  turns: publicProcedure
    .input(limitInput)
    .query(({ input }) => tailJsonl(turnsPath(), TurnSchema, { maxLines: input.limit })),

  /** Closed round-trip trades, tail-read. */
  trades: publicProcedure
    .input(limitInput)
    .query(({ input }) => tailJsonl(tradesPath(), TradeSchema, { maxLines: input.limit })),

  /** Latest decision-quality metrics (most recent quality/<date>.json), or null. */
  quality: publicProcedure.query(async () => {
    const latest = await latestQualityFile();
    if (latest === null) return null;
    const metrics = await readJsonFile(latest.path, QualitySchema);
    return metrics === null ? null : { date: latest.date, metrics };
  }),

  /** System health verdict (steering/health.json), or null when absent. */
  health: publicProcedure.query(() => readJsonFile(healthPath(), HealthSchema)),

  /** Opaque watchlist / regime markdown (workspace/*.md), or null. */
  watchlist: publicProcedure.query((): Promise<MarkdownDoc | null> => readMarkdownDoc(watchlistPath())),
  regime: publicProcedure.query((): Promise<MarkdownDoc | null> => readMarkdownDoc(regimePath())),
});

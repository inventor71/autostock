import { promises as fs } from "node:fs";
import type { ZodType } from "zod";

/**
 * Surface-specific safe readers (C2). All of them are fail-honest: any failure
 * returns null / [] and logs a warning — they never throw and never invent
 * placeholder data (BR-8).
 */

// Polling hits these readers every few seconds; dedupe warnings so a missing
// file logs once, not forever.
const lastWarnByKey = new Map<string, string>();

function warnOnce(key: string, message: string): void {
  if (lastWarnByKey.get(key) === message) return;
  lastWarnByKey.set(key, message);
  console.warn(`[viz-shell:safe-read] ${message}`);
}

function clearWarn(key: string): void {
  lastWarnByKey.delete(key);
}

function isEnoent(err: unknown): boolean {
  return (err as NodeJS.ErrnoException)?.code === "ENOENT";
}

/** L2a — atomic-producer JSON file (steering/snapshot.json). */
export async function readJsonFile<T>(
  filePath: string,
  schema: ZodType<T>,
): Promise<T | null> {
  let raw: string;
  try {
    raw = await fs.readFile(filePath, "utf8");
  } catch (err) {
    warnOnce(
      `read:${filePath}`,
      isEnoent(err)
        ? `${filePath} missing (daemon not running?)`
        : `${filePath} unreadable: ${String(err)}`,
    );
    return null;
  }
  clearWarn(`read:${filePath}`);
  try {
    return schema.parse(JSON.parse(raw));
  } catch (err) {
    // Schema drift signal — the producer is atomic, so this should not happen
    // on the happy path.
    warnOnce(`parse:${filePath}`, `${filePath} parse failed: ${String(err)}`);
    return null;
  }
}

const TAIL_MAX_BYTES = 8 * 1024 * 1024;

/**
 * L2b — append-only JSONL tail (workspace/equity.jsonl). Only complete
 * ('\n'-terminated) lines are considered; a torn final line is discarded.
 * Lines that fail JSON/schema parsing are skipped (counted, logged).
 */
export async function tailJsonl<T>(
  filePath: string,
  schema: ZodType<T>,
  opts: { maxLines?: number } = {},
): Promise<T[]> {
  const maxLines = opts.maxLines ?? 365;

  let handle: fs.FileHandle;
  try {
    handle = await fs.open(filePath, "r");
  } catch (err) {
    warnOnce(
      `read:${filePath}`,
      isEnoent(err)
        ? `${filePath} missing (daemon not running?)`
        : `${filePath} unreadable: ${String(err)}`,
    );
    return [];
  }

  let text: string;
  let truncatedHead: boolean;
  try {
    const { size } = await handle.stat();
    const offset = Math.max(0, size - TAIL_MAX_BYTES);
    truncatedHead = offset > 0;
    const buf = Buffer.alloc(size - offset);
    await handle.read(buf, 0, buf.length, offset);
    text = buf.toString("utf8");
  } finally {
    await handle.close();
  }
  clearWarn(`read:${filePath}`);

  const lines = text.split("\n");
  // Tail started mid-line: the first element is a partial line.
  if (truncatedHead) lines.shift();
  // No trailing '\n' means the writer is mid-append — discard the torn line.
  if (lines.length > 0 && lines[lines.length - 1] !== "") lines.pop();

  const records: T[] = [];
  let skipped = 0;
  for (const line of lines) {
    if (line.trim() === "") continue;
    try {
      records.push(schema.parse(JSON.parse(line)));
    } catch {
      skipped += 1;
    }
  }
  if (skipped > 0) {
    warnOnce(`skip:${filePath}`, `${filePath}: skipped ${skipped} unparsable line(s)`);
  } else {
    clearWarn(`skip:${filePath}`);
  }
  return records.slice(-maxLines);
}

/**
 * L2c — stat-stable read for non-atomic producers (workspace/positions/*.md).
 * stat → read → stat; retry with backoff while the file is moving under us.
 * On retry exhaustion the last read is returned flagged stale (fail-honest).
 */
export async function readFileStable(
  filePath: string,
  opts: { retries?: number } = {},
): Promise<{ content: string; mtimeMs: number; stale: boolean } | null> {
  const retries = opts.retries ?? 3;

  let content = "";
  let mtimeMs = 0;
  for (let attempt = 1; attempt <= retries; attempt++) {
    let s1: { mtimeMs: number; size: number };
    try {
      s1 = await fs.stat(filePath);
      content = await fs.readFile(filePath, "utf8");
      const s2 = await fs.stat(filePath);
      mtimeMs = s2.mtimeMs;
      if (
        s1.mtimeMs === s2.mtimeMs &&
        s1.size === s2.size &&
        s2.size === Buffer.byteLength(content, "utf8")
      ) {
        clearWarn(`stable:${filePath}`);
        return { content, mtimeMs, stale: false };
      }
    } catch (err) {
      if (isEnoent(err)) return null;
      warnOnce(`stable:${filePath}`, `${filePath} unreadable: ${String(err)}`);
      return null;
    }
    await new Promise((r) => setTimeout(r, 50 * attempt));
  }
  warnOnce(`stable:${filePath}`, `${filePath} kept changing during read — serving stale copy`);
  return { content, mtimeMs, stale: true };
}

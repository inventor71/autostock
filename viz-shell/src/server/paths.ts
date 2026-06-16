import path from "node:path";

/**
 * Read-target whitelist. These constants are the ONLY filesystem locations the
 * data routers may touch — no procedure accepts a path as input (BR-7).
 */

/** viz-shell app directory (next dev runs with cwd = viz-shell/). */
export function vizShellDir(): string {
  return process.cwd();
}

/**
 * autostock repo root that holds the daemon artifacts (steering/, workspace/).
 * Defaults to the parent of viz-shell/. Override with AUTOSTOCK_ROOT when the
 * live data lives in another checkout (e.g. running from a git worktree).
 */
export function repoRoot(): string {
  return process.env.AUTOSTOCK_ROOT ?? path.resolve(vizShellDir(), "..");
}

export function snapshotPath(): string {
  return path.join(repoRoot(), "steering", "snapshot.json");
}

export function equityPath(): string {
  return path.join(repoRoot(), "workspace", "equity.jsonl");
}

export function decisionsPath(): string {
  return path.join(repoRoot(), "workspace", "decisions.jsonl");
}

export function healthPath(): string {
  return path.join(repoRoot(), "steering", "health.json");
}

export function qualityDir(): string {
  return path.join(repoRoot(), "workspace", "quality");
}

export function watchlistPath(): string {
  return path.join(repoRoot(), "workspace", "watchlist.md");
}

export function regimePath(): string {
  return path.join(repoRoot(), "workspace", "regime.md");
}

export function lessonsPath(): string {
  return path.join(repoRoot(), "workspace", "lessons.md");
}

/** Dated-artifact directories (one file per ET date). */
export function screeningDir(): string {
  return path.join(repoRoot(), "workspace", "screening");
}
export function sentimentDir(): string {
  return path.join(repoRoot(), "workspace", "sentiment");
}
export function surgeDir(): string {
  return path.join(repoRoot(), "workspace", "surge");
}
export function dailyDir(): string {
  return path.join(repoRoot(), "workspace", "daily");
}

export function turnsPath(): string {
  return path.join(repoRoot(), "workspace", "turns.jsonl");
}

export function tradesPath(): string {
  return path.join(repoRoot(), "workspace", "trades.jsonl");
}

export function positionsDir(): string {
  return path.join(repoRoot(), "workspace", "positions");
}

/** Where the chat agent is allowed to write (boundary: BR-1). */
export function generatedDir(): string {
  return path.join(vizShellDir(), "src", "generated");
}

/** Single-session persistence (BR-14). Gitignored. */
export function sessionFilePath(): string {
  return path.join(vizShellDir(), ".cache", "session.json");
}

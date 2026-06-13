/** Pure helpers for generated-view discovery and tab visibility (L4 / BR-13). */

export const HIDDEN_VIEWS_KEY = "viz-shell.hidden-views";

/** "pnl-by-symbol.tsx" → "Pnl By Symbol" (fallback when a view exports no meta.title). */
export function fileNameToTitle(fileName: string): string {
  return fileName
    .replace(/\.tsx$/, "")
    .split(/[-_]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/** Files starting with "_" are utilities/examples — never shown as tabs (BR-10). */
export function isTabFile(fileName: string): boolean {
  return fileName.endsWith(".tsx") && !fileName.startsWith("_");
}

export function hideView(hidden: string[], fileName: string): string[] {
  return hidden.includes(fileName) ? hidden : [...hidden, fileName];
}

export function restoreView(hidden: string[], fileName: string): string[] {
  return hidden.filter((f) => f !== fileName);
}

/** localStorage read — tolerant of corrupt/absent values. */
export function loadHiddenViews(storage: Pick<Storage, "getItem">): string[] {
  try {
    const parsed: unknown = JSON.parse(storage.getItem(HIDDEN_VIEWS_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

export function saveHiddenViews(storage: Pick<Storage, "setItem">, hidden: string[]): void {
  try {
    storage.setItem(HIDDEN_VIEWS_KEY, JSON.stringify(hidden));
  } catch {
    // storage unavailable — visibility simply won't persist
  }
}

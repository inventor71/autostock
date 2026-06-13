import { describe, expect, it } from "vitest";

import {
  HIDDEN_VIEWS_KEY,
  fileNameToTitle,
  hideView,
  isTabFile,
  loadHiddenViews,
  restoreView,
  saveHiddenViews,
} from "@/lib/view-utils";

describe("fileNameToTitle", () => {
  it.each([
    ["pnl-by-symbol.tsx", "Pnl By Symbol"],
    ["risk.tsx", "Risk"],
    ["my_view-2.tsx", "My View 2"],
  ])("%s → %s", (file, title) => {
    expect(fileNameToTitle(file)).toBe(title);
  });
});

describe("isTabFile (BR-10: '_' prefix excluded)", () => {
  it.each([
    ["pnl.tsx", true],
    ["_example.tsx", false],
    ["_utils.tsx", false],
    ["readme.md", false],
  ])("%s → %s", (file, expected) => {
    expect(isTabFile(file)).toBe(expected);
  });
});

describe("hide/restore (BR-13: display state only)", () => {
  it("hideView adds once (idempotent)", () => {
    expect(hideView([], "a.tsx")).toEqual(["a.tsx"]);
    expect(hideView(["a.tsx"], "a.tsx")).toEqual(["a.tsx"]);
  });

  it("restoreView removes only the target", () => {
    expect(restoreView(["a.tsx", "b.tsx"], "a.tsx")).toEqual(["b.tsx"]);
    expect(restoreView(["b.tsx"], "missing.tsx")).toEqual(["b.tsx"]);
  });
});

describe("localStorage persistence", () => {
  function memoryStorage(initial?: string) {
    const store = new Map<string, string>();
    if (initial !== undefined) store.set(HIDDEN_VIEWS_KEY, initial);
    return {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      dump: () => store.get(HIDDEN_VIEWS_KEY),
    };
  }

  it("round-trips a hidden list", () => {
    const s = memoryStorage();
    saveHiddenViews(s, ["a.tsx", "b.tsx"]);
    expect(loadHiddenViews(s)).toEqual(["a.tsx", "b.tsx"]);
  });

  it("tolerates corrupt values", () => {
    expect(loadHiddenViews(memoryStorage("{nope"))).toEqual([]);
    expect(loadHiddenViews(memoryStorage('{"not":"array"}'))).toEqual([]);
    expect(loadHiddenViews(memoryStorage('["ok", 42]'))).toEqual(["ok"]);
  });

  it("returns [] when nothing stored", () => {
    expect(loadHiddenViews(memoryStorage())).toEqual([]);
  });
});

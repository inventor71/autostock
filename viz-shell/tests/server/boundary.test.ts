import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterAll, beforeEach, describe, expect, it } from "vitest";

import { createBoundary, type DeniedEvent } from "@/server/chat/boundary";

/**
 * Boundary denial tests — success criterion ③ of the security baseline.
 * Every rule extension to checkBoundary must add cases here.
 */

const root = mkdtempSync(path.join(os.tmpdir(), "viz-boundary-"));
const vizDir = path.join(root, "viz-shell");
const genDir = path.join(vizDir, "src", "generated");
const outsideDir = path.join(root, "workspace"); // simulates daemon data dir
mkdirSync(genDir, { recursive: true });
mkdirSync(outsideDir, { recursive: true });
writeFileSync(path.join(outsideDir, "secret.md"), "thesis body");

afterAll(() => rmSync(root, { recursive: true, force: true }));

let denials: DeniedEvent[] = [];
const boundary = createBoundary({
  vizShellDir: vizDir,
  generatedDir: genDir,
  onDeny: (ev) => denials.push(ev),
});

beforeEach(() => {
  denials = [];
});

describe("write tools (BR-1)", () => {
  it.each(["Write", "Edit", "MultiEdit", "NotebookEdit"])(
    "%s inside src/generated/ is allowed",
    (tool) => {
      const res = boundary(tool, { file_path: path.join(genDir, "view.tsx") });
      expect(res.behavior).toBe("allow");
    },
  );

  it("relative path resolving into src/generated/ is allowed", () => {
    expect(boundary("Write", { file_path: "src/generated/pnl.tsx" }).behavior).toBe("allow");
  });

  const writeDenials: Array<[string, string]> = [
    ["viz-shell file outside generated/", "src/app/page.tsx"],
    ["parent-directory escape", "src/generated/../../package.json"],
    ["repo escape via ../", "../workspace/secret.md"],
    ["absolute path outside", "/etc/passwd"],
  ];
  it.each(writeDenials)("Write denied: %s", (_label, p) => {
    const res = boundary("Write", { file_path: p });
    expect(res.behavior).toBe("deny");
    if (res.behavior === "deny") expect(res.message).toContain("src/generated/");
    expect(denials).toHaveLength(1);
  });

  it("symlinked file inside generated/ pointing outside is denied", () => {
    const link = path.join(genDir, "evil.tsx");
    symlinkSync(path.join(outsideDir, "secret.md"), link);
    expect(boundary("Write", { file_path: link }).behavior).toBe("deny");
  });

  it("path under a symlinked dir inside generated/ pointing outside is denied", () => {
    const dirLink = path.join(genDir, "sub");
    symlinkSync(outsideDir, dirLink);
    expect(
      boundary("Write", { file_path: path.join(dirLink, "new.tsx") }).behavior,
    ).toBe("deny");
  });
});

describe("read tools (BR-2)", () => {
  it("Read inside viz-shell is allowed", () => {
    expect(boundary("Read", { file_path: path.join(vizDir, "src", "x.ts") }).behavior).toBe("allow");
  });

  it("Glob with no path operates on cwd — allowed", () => {
    expect(boundary("Glob", { pattern: "**/*.tsx" }).behavior).toBe("allow");
  });

  it.each([
    ["Read", { file_path: "../workspace/secret.md" }],
    ["Read", { file_path: "/etc/hosts" }],
    ["Grep", { pattern: "key", path: "/tmp" }],
    ["Glob", { pattern: "../**/*.md" }],
  ] as Array<[string, Record<string, unknown>]>)(
    "%s outside viz-shell is denied with reason",
    (tool, input) => {
      const res = boundary(tool, input);
      expect(res.behavior).toBe("deny");
      if (res.behavior === "deny") expect(res.message).toContain("viz-shell");
      expect(denials[0]?.reason).toBeTruthy();
    },
  );
});

describe("deny-by-default for all other tools (BR-3)", () => {
  it.each(["Bash", "WebFetch", "WebSearch", "Task", "KillShell", "mcp__steer__write", "FutureTool"])(
    "%s is denied",
    (tool) => {
      const res = boundary(tool, {});
      expect(res.behavior).toBe("deny");
      if (res.behavior === "deny") expect(res.message).toContain("not permitted");
    },
  );
});

describe("deny event surface (UI ⚠️)", () => {
  it("onDeny carries tool, target and reason", () => {
    boundary("Bash", { command: "rm -rf /" });
    expect(denials).toEqual([
      { tool: "Bash", target: "Bash", reason: expect.stringContaining("not permitted") },
    ]);
  });
});

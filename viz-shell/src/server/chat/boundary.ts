import fs from "node:fs";
import path from "node:path";

/**
 * The single write gate for the chat agent (L1). Deny-by-default:
 *   - Write/Edit-class tools: allowed only under <viz-shell>/src/generated/
 *   - Read/Glob/Grep:         allowed only under <viz-shell>/
 *   - every other tool:       denied
 * Any extension of these rules MUST come with boundary test cases.
 */

const WRITE_TOOLS = new Set(["Write", "Edit", "MultiEdit", "NotebookEdit"]);
const READ_TOOLS = new Set(["Read", "Glob", "Grep"]);

export type BoundaryDecision =
  | { behavior: "allow"; updatedInput: Record<string, unknown> }
  | { behavior: "deny"; message: string };

export type DeniedEvent = { tool: string; target: string; reason: string };

export type BoundaryOptions = {
  vizShellDir: string;
  generatedDir: string;
  onDeny?: (ev: DeniedEvent) => void;
};

/**
 * Resolve symlinks via the nearest EXISTING ancestor so a link cannot smuggle
 * the target outside the boundary, even for not-yet-created files.
 */
function realResolve(absPath: string): string {
  let dir = absPath;
  const trailing: string[] = [];
  for (;;) {
    try {
      const real = fs.realpathSync(dir);
      return path.join(real, ...trailing.reverse());
    } catch {
      const parent = path.dirname(dir);
      if (parent === dir) return absPath; // hit fs root without resolving
      trailing.push(path.basename(dir));
      dir = parent;
    }
  }
}

function isWithin(base: string, target: string): boolean {
  const rel = path.relative(base, target);
  return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
}

function extractRawPath(toolName: string, input: Record<string, unknown>): string | null {
  for (const key of ["file_path", "notebook_path", "path"]) {
    const v = input[key];
    if (typeof v === "string" && v.length > 0) return v;
  }
  // An absolute Glob pattern is treated as the target itself via its static
  // prefix. ".."-containing patterns never reach here — they are denied
  // outright in checkBoundary (a metachar before the ".." would erase it from
  // the static prefix and smuggle the traversal past this check).
  const pattern = input["pattern"];
  if (toolName === "Glob" && typeof pattern === "string" && path.isAbsolute(pattern)) {
    return pattern.replace(/[*?[].*$/, ""); // static prefix of the glob
  }
  return null;
}

export function createBoundary(opts: BoundaryOptions) {
  const vizShellRoot = realResolve(path.resolve(opts.vizShellDir));
  const generatedRoot = realResolve(path.resolve(opts.generatedDir));

  return function checkBoundary(
    toolName: string,
    input: Record<string, unknown>,
  ): BoundaryDecision {
    const deny = (target: string, reason: string): BoundaryDecision => {
      opts.onDeny?.({ tool: toolName, target, reason });
      console.warn(`[viz-shell:boundary] deny ${toolName} ${target}: ${reason}`);
      return { behavior: "deny", message: reason };
    };

    const isWrite = WRITE_TOOLS.has(toolName);
    const isRead = READ_TOOLS.has(toolName);
    if (!isWrite && !isRead) {
      return deny(toolName, `tool '${toolName}' is not permitted in viz-shell`);
    }

    // Glob patterns may not climb: the static-prefix extraction below cannot
    // see a ".." that follows a metachar ("**/../../x" → prefix ""), so the
    // traversal would otherwise escape the read boundary at glob-engine level.
    const pattern = input["pattern"];
    if (toolName === "Glob" && typeof pattern === "string" && pattern.includes("..")) {
      return deny(pattern, "glob patterns must not contain '..' in viz-shell");
    }

    const raw = extractRawPath(toolName, input);
    // No path on a read tool = operate on cwd (viz-shell) — inside the boundary.
    const abs =
      raw === null
        ? vizShellRoot
        : realResolve(path.resolve(vizShellRoot, raw));

    if (isWrite) {
      if (isWithin(generatedRoot, abs)) {
        return { behavior: "allow", updatedInput: input };
      }
      return deny(
        raw ?? toolName,
        "writes are restricted to src/generated/ — create the view file there",
      );
    }

    if (isWithin(vizShellRoot, abs)) {
      return { behavior: "allow", updatedInput: input };
    }
    return deny(
      raw ?? toolName,
      "reads are restricted to the viz-shell directory",
    );
  };
}

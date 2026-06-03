import { readFileSync, existsSync } from "fs"
import { join, resolve, normalize } from "path"

export interface ThesisContent {
  symbol: string
  markdown: string
  exists: boolean
}

export function readThesis(workspaceDir: string, symbol: string): ThesisContent {
  const safe = symbol.replace(/[^A-Za-z0-9.-]/g, "").toUpperCase()
  if (!safe) return { symbol, markdown: "", exists: false }

  const base = resolve(workspaceDir, "positions")
  const target = normalize(join(base, `${safe}.md`))

  // SECURITY-03: path traversal guard
  if (!target.startsWith(base)) {
    return { symbol, markdown: "", exists: false }
  }

  if (!existsSync(target)) {
    return { symbol, markdown: "", exists: false }
  }

  try {
    return { symbol: safe, markdown: readFileSync(target, "utf-8"), exists: true }
  } catch {
    return { symbol: safe, markdown: "", exists: false }
  }
}

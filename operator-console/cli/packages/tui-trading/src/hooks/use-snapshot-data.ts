import { readFileSync } from "fs"
import { join } from "path"
import type { PositionInfo } from "../types"

export function readPositions(steeringDir: string): Record<string, PositionInfo> {
  try {
    const raw = readFileSync(join(steeringDir, "snapshot.json"), "utf-8")
    const snap = JSON.parse(raw)
    return (snap.positions ?? {}) as Record<string, PositionInfo>
  } catch {
    return {}
  }
}

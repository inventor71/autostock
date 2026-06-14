// F79 C9 — LockController core (client-only inactivity lock, NFR-6). Pure decision logic
// with an injected clock so it is unit-testable; the SolidJS view binds the signal, resets
// on activity (touch), and renders the lock overlay. Lock is CLIENT-ONLY (D-AD-4): the
// server connection / event stream stay alive; only mutating actions (C3) are refused until
// re-auth, and the shell is curtained.

export const DEFAULT_LOCK_TIMEOUT_MS = 300_000 // 5 min

/** True when inactivity has reached the timeout (>= so a 0 timeout locks immediately). */
export function shouldLock(lastActivityMs: number, nowMs: number, timeoutMs: number): boolean {
  return nowMs - lastActivityMs >= timeoutMs
}

/** Milliseconds until auto-lock from `lastActivity` (0 when already due). */
export function msUntilLock(lastActivityMs: number, nowMs: number, timeoutMs: number): number {
  return Math.max(0, timeoutMs - (nowMs - lastActivityMs))
}

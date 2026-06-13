/**
 * Single-flight guard for chat turns (BR-15): one operator, one in-flight turn.
 * Module-level state is fine — the dev server is a single Node process.
 */
let inFlight = false;

export function tryAcquireTurn(): boolean {
  if (inFlight) return false;
  inFlight = true;
  return true;
}

export function releaseTurn(): void {
  inFlight = false;
}

import { createSignal, onCleanup } from "solid-js"
import { readFileSync } from "fs"
import { join } from "path"

// F95: one symbol's entry in the daemon-written steering/quotes.json warm cache.
// Either a live price or an error marker (so the panel can distinguish "시세 없음"
// from a symbol that was never fetched — which shows as null → "조회 중").
export interface QuoteEntry {
  price?: number
  error?: string
  ts: string
}

/** Read the clicked symbol's quote from steering/quotes.json. Null when the file
 *  is absent/unreadable or the symbol isn't cached (TUI shows "조회 중"). */
export function readQuote(steeringDir: string, symbol: string): QuoteEntry | null {
  if (!steeringDir || !symbol) return null
  try {
    const raw = readFileSync(join(steeringDir, "quotes.json"), "utf-8")
    const data = JSON.parse(raw)
    return (data?.quotes?.[symbol.toUpperCase()] ?? null) as QuoteEntry | null
  } catch {
    return null
  }
}

function sameQuote(a: QuoteEntry | null, b: QuoteEntry | null): boolean {
  if (a === b) return true
  if (!a || !b) return false
  return a.price === b.price && a.error === b.error && a.ts === b.ts
}

/** Poll the warm cache for `symbol()` on an interval. `symbol` is an accessor so
 *  the same overlay instance can re-target when the user clicks another symbol.
 *  Only updates the signal when the entry actually changes (avoids overlay
 *  repaint flicker, mirroring useMonitorData). */
export function useQuote(steeringDir: string, symbol: () => string, intervalMs = 1500) {
  const [quote, setQuote] = createSignal<QuoteEntry | null>(readQuote(steeringDir, symbol()))
  const tick = () => {
    const next = readQuote(steeringDir, symbol())
    setQuote((prev) => (sameQuote(prev, next) ? prev : next))
  }
  tick()
  const timer = setInterval(tick, intervalMs)
  onCleanup(() => clearInterval(timer))
  return quote
}

import type { TuiPlugin, TuiPluginApi } from "@opencode-ai/plugin/tui"
import type { InternalTuiPlugin } from "../../plugin/internal"
import { createSignal, For, onCleanup, Show } from "solid-js"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { orderRole, orderTrigger, orderDelta, pnlPct, fmtPct, fmtPrice, fillDatePrefix } from "./sidebar-format"

// F4 Unit B (Phase 2) — autostock steering sidebar panel. Reads the daemon's live
// read-view (steering/snapshot.json) + the event tail (steering/events.jsonl), both
// published by Unit A, and shows run-state / market / positions / open-orders /
// pending-approvals / recent events. Read-only (no order authority); polls the files
// (no daemon round-trip). Paths from STEERING_DIR (same as the MCP server).

const id = "internal:sidebar-autostock"
const EVENT_TAIL = 5
// F5 S6 (BR-8): runtime-disconnect banner. The daemon publishes the snapshot every ~5s; if
// published_at goes stale past this, the daemon is down/wedged or the channel is broken — surface
// it loudly instead of a silently-frozen panel. Generous vs the 5s cadence to avoid false alarms
// during a busy LLM turn (mirrors the launcher's health window rationale).
const SNAPSHOT_STALE_MS = 30_000

interface Order {
  symbol?: string
  order_id?: string
  stop_price?: number | null
  limit_price?: number | null
  side?: string // F8: "buy" | "sell"
  order_type?: string // F8: "limit" | "stop" | "stop_limit" | ... (role derivation)
  current_price?: number | null // F8: held → position price, else PriceBook (Δ-to-trigger)
}

// F8: a held position with status.py-rich fields (current price + P&L).
interface PositionRow {
  qty?: number
  avg_entry_price?: number
  current_price?: number
  market_value?: number
  unrealized_pnl?: number
}

// F8: a recent broker fill (what was bought / sold).
interface RecentFill {
  ts?: string
  side?: string
  qty?: number
  symbol?: string
  price?: number
}

interface QueuedTrade {
  id?: string
  verb?: string
  args?: { symbol?: string; size?: number; unit?: string }
}

interface Account {
  equity?: number
  cash?: number
  invested?: number // F8
  open_pnl?: number
  position_count?: number
}

interface RoundTrip {
  closed_count?: number
  win_rate?: number | null
  realized_pnl?: number
}

interface Snap {
  run_state?: { paused?: boolean; entries_halted?: boolean }
  market_open?: boolean
  positions?: Record<string, PositionRow>
  open_orders?: Order[]
  pending?: unknown[]
  queued_trades?: QueuedTrade[]
  locked_symbols?: Record<string, string | null>
  account?: Account // F6 FR-2
  round_trip?: RoundTrip // F6 FR-3
  recent_fills?: RecentFill[] // F8 FR-3
}

interface Event {
  ts?: string
  kind?: string
  payload?: Record<string, unknown>
}

function readSnap(): Snap | null {
  const dir = process.env.STEERING_DIR
  if (!dir) return null
  try {
    return JSON.parse(readFileSync(join(dir, "snapshot.json"), "utf8")) as Snap
  } catch {
    return null
  }
}

// Tail the append-only event log, torn-line-safe: drop an incomplete trailing line
// (a write may be mid-flight) and parse only the last EVENT_TAIL complete records.
function readEvents(): Event[] {
  const dir = process.env.STEERING_DIR
  if (!dir) return []
  let text: string
  try {
    text = readFileSync(join(dir, "events.jsonl"), "utf8")
  } catch {
    return []
  }
  const lines = text.split("\n")
  if (!text.endsWith("\n")) lines.pop() // trailing partial write — not yet complete
  const complete = lines.filter((l) => l.trim().length > 0)
  const out: Event[] = []
  for (const line of complete.slice(-EVENT_TAIL)) {
    try {
      out.push(JSON.parse(line) as Event)
    } catch {
      // skip a corrupt/partial record without dropping the rest
    }
  }
  return out
}

// A generous safety bound only — the event <text> uses wrapMode="word", so normal
// lines wrap to the sidebar width and show in full (no "…" truncation). This just keeps
// a pathological mega-payload from wrapping into dozens of lines.
const LINE_MAX = 160

function clip(s: string, max = LINE_MAX): string {
  const t = s.trimEnd()
  return t.length > max ? t.slice(0, max - 1) + "…" : t
}

function hhmm(ts?: string): string {
  if (!ts) return ""
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ""
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")} `
}

// A leading status glyph so the operator can scan outcomes at a glance instead of
// reading JSON: ✓ done/accepted, · deferred/queued/pending, ✗ rejected/denied/error.
// All width-1 (no emoji) to keep the narrow sidebar aligned across terminals.
function outcomeGlyph(o: string): string {
  if (/reject|deny|denied|error|fail|invalid|bad/i.test(o)) return "✗"
  if (/defer|queue|pending|await|wait/i.test(o)) return "·"
  return "✓"
}

function str(v: unknown): string {
  return v == null ? "" : typeof v === "object" ? JSON.stringify(v) : String(v)
}

// Render one event as a compact human line (no raw JSON). Falls back to `key=val`
// pairs for kinds we don't special-case, which still reads far better than a JSON blob.
function eventLine(e: Event): string {
  const t = hhmm(e.ts)
  const p = e.payload ?? {}
  switch (e.kind) {
    case "outcome": {
      const o = str(p["outcome"]) || "?"
      const detail = str(p["detail"])
      return clip(`${t}${outcomeGlyph(o)} ${o}${detail ? ` · ${detail}` : ""}`)
    }
    case "agent_question":
      return clip(`${t}? ${str(p["symbol"])}: ${str(p["text"])}`)
    case "fill":
      return clip(`${t}• fill ${str(p["symbol"])} ${str(p["qty"])}@${str(p["price"])}`)
    case "lifecycle":
      return clip(`${t}${str(p["state"]) || "lifecycle"}${p["detail"] ? ` · ${str(p["detail"])}` : ""}`)
    default: {
      const kv = Object.entries(p)
        .map(([k, v]) => `${k}=${str(v)}`)
        .join(" ")
      return clip(`${t}${e.kind ?? "?"}${kv ? ` ${kv}` : ""}`)
    }
  }
}

// F6 — compact money / signed-P&L formatting for the account + performance blocks.
function fmtMoney(n?: number): string {
  if (n == null || !Number.isFinite(n)) return "—"
  return (n < 0 ? "-$" : "$") + Math.abs(Math.round(n)).toLocaleString("en-US")
}

function fmtPnl(n?: number): string {
  if (n == null || !Number.isFinite(n)) return "—"
  return (n >= 0 ? "+$" : "-$") + Math.abs(Math.round(n)).toLocaleString("en-US")
}

function View(props: { api: TuiPluginApi }) {
  const [snap, setSnap] = createSignal<Snap | null>(readSnap())
  const [events, setEvents] = createSignal<Event[]>(readEvents())
  const timer = setInterval(() => {
    setSnap(readSnap())
    setEvents(readEvents())
  }, 1500)
  onCleanup(() => clearInterval(timer))

  const theme = () => props.api.theme.current
  // F5 S6 (BR-8): compute a disconnect reason from what the sidebar can observe (channel/snapshot
  // freshness). published_at is naive-local ISO → new Date() parses it as local (same host).
  // Secrets are never shown. null = connected.
  const disconnect = (): string | null => {
    if (!process.env.STEERING_DIR) return "STEERING_DIR not set — launch via `autostock`"
    const s = snap()
    if (!s) return "no snapshot — daemon not publishing (starting up / down?)"
    const pub = (s as { published_at?: string }).published_at
    const age = pub ? Date.now() - new Date(pub).getTime() : NaN
    if (Number.isNaN(age)) return "snapshot has no published_at — channel broken?"
    if (age > SNAPSHOT_STALE_MS) return `daemon snapshot stale ${Math.round(age / 1000)}s — daemon down/wedged?`
    return null
  }
  const runLabel = () => {
    const r = snap()?.run_state
    if (!r) return "?"
    if (r.paused) return "PAUSED"
    if (r.entries_halted) return "HALT-ENTRIES"
    return "RUNNING"
  }
  const positions = () => Object.entries(snap()?.positions ?? {})
  const orders = () => snap()?.open_orders ?? []
  const queued = () => snap()?.queued_trades ?? []
  const pendingN = () => (snap()?.pending ?? []).length
  const account = () => snap()?.account
  const rt = () => snap()?.round_trip
  const pnlColor = (n?: number) => ((n ?? 0) >= 0 ? theme().success : theme().error)

  const queuedLine = (q: QueuedTrade): string => {
    const a = q.args ?? {}
    const sized = a.size != null ? ` ${a.size}${a.unit ?? ""}` : ""
    return `${q.verb ?? "?"} ${a.symbol ?? "?"}${sized}  ${(q.id ?? "").slice(0, 8)}`
  }

  return (
    <box>
      {/* F26 — supervisor-mode badge. Shown ONLY when the console was launched via
          `autostock --supervisor` (developer-only, read-only whole-codebase analysis),
          so the operator never confuses an elevated session with a normal one. Always
          evaluated (independent of the daemon snapshot). */}
      <Show when={process.env.AUTOSTOCK_SUPERVISOR === "on"}>
        <text fg={theme().warning}>
          <b>MODE: SUPERVISOR</b> · read-only
        </text>
      </Show>
      {/* F5 S6: disconnect banner — always evaluated, even when there is no snapshot to show. */}
      <Show when={disconnect()}>
        <text fg={theme().text} wrapMode="word">
          ⚠ {disconnect()}
        </text>
      </Show>
      <Show when={snap()}>
        <box>
          <box flexDirection="row" gap={1}>
            <text fg={theme().text}>
              <b>autostock</b>
            </text>
            <text fg={theme().text}>
              {runLabel()}
              {snap()?.market_open ? " · MKT OPEN" : " · MKT CLOSED"}
            </text>
          </box>
        {/* F6 FR-2/5 — account summary (hidden until the daemon publishes it, BR-8). */}
        <Show when={account()}>
          {(a) => (
            <box flexDirection="row" gap={1}>
              <text fg={theme().textMuted}>eq</text>
              <text fg={theme().text}>{fmtMoney(a().equity)}</text>
              <text fg={theme().textMuted}>cash</text>
              <text fg={theme().text}>{fmtMoney(a().cash)}</text>
              <Show when={a().invested != null}>
                <text fg={theme().textMuted}>inv</text>
                <text fg={theme().text}>{fmtMoney(a().invested)}</text>
              </Show>
              <text fg={theme().textMuted}>pnl</text>
              <text fg={pnlColor(a().open_pnl)}>{fmtPnl(a().open_pnl)}</text>
            </box>
          )}
        </Show>
        {/* F6 FR-3/5 — today's realized round-trip performance (empty state when none). */}
        <Show when={rt()}>
          {(r) => (
            <Show
              when={(r().closed_count ?? 0) > 0}
              fallback={<text fg={theme().textMuted}>today · no closed trades</text>}
            >
              <box flexDirection="row" gap={1}>
                <text fg={theme().textMuted}>today</text>
                <text fg={theme().text}>
                  W {Math.round((r().win_rate ?? 0) * 100)}% ({r().closed_count})
                </text>
                <text fg={pnlColor(r().realized_pnl)}>{fmtPnl(r().realized_pnl)}</text>
              </box>
            </Show>
          )}
        </Show>
        <Show when={pendingN() > 0}>
          <text fg={theme().text}>pending approvals: {pendingN()} — /pending</text>
        </Show>
        {/* F8 FR-1/5 — holdings: qty · current price · signed P&L $ + %. The whole row
            is colored by P&L sign (green up / red down); arrows are in the text. One
            <text wrapMode="word"> so it wraps when dragged wider (OpenTUI has no inline
            color span — coloring is per-<text>). */}
        <For each={positions()}>
          {([sym, p]) => {
            const pct = pnlPct(p)
            const hasPnl = p?.unrealized_pnl != null
            const price = p?.current_price != null ? ` @${fmtPrice(p.current_price)}` : ""
            const lock = snap()?.locked_symbols?.[sym] ? " (locked)" : ""
            const pnl = hasPnl
              ? `  ${fmtPnl(p.unrealized_pnl)}${pct != null ? ` ${fmtPct(pct)}` : ""}`
              : ""
            return (
              <text fg={hasPnl ? pnlColor(p.unrealized_pnl) : theme().text} wrapMode="word">
                {sym} {String(p?.qty ?? "?")}
                {price}
                {lock}
                {pnl}
              </text>
            )
          }}
        </For>
        {/* F8 FR-2/5 — resting orders: role · trigger · Δ-to-trigger %. Row colored by Δ
            direction when we have a current price, else neutral. */}
        <Show when={orders().length > 0}>
          {/* F13 — blank line before each section header for visual separation. */}
          <text fg={theme().textMuted} marginTop={1}>orders</text>
          <For each={orders()}>
            {(o) => {
              const trig = orderTrigger(o)
              const d = orderDelta(o)
              const trigStr = trig != null ? ` ${fmtPrice(trig)}` : ""
              const dStr = d != null ? `  ${fmtPct(d)}` : ""
              const side = (o.side ?? "").toLowerCase()
              return (
                <text fg={d != null ? pnlColor(d) : side === "sell" ? theme().error : side === "buy" ? theme().success : theme().text} wrapMode="word">
                  {o.symbol ?? "?"} {orderRole(o)}
                  {trigStr}
                  {dStr}
                </text>
              )
            }}
          </For>
        </Show>
        {/* F8 FR-3/5 — recent fills (what was bought / sold): date · time · side · qty ·
            sym · price. Row colored by side (BUY green / SELL red). F13: the list can span
            days, so prefix the local MM/DD — shown only when it changes vs the previous row
            (blank-padded otherwise so HH:MM stays aligned). */}
        <Show when={(snap()?.recent_fills ?? []).length > 0}>
          <text fg={theme().textMuted} marginTop={1}>fills</text>
          <For each={snap()?.recent_fills ?? []}>
            {(f, i) => {
              const buy = (f.side ?? "").toLowerCase() === "buy"
              const prev = i() > 0 ? (snap()?.recent_fills ?? [])[i() - 1] : undefined
              return (
                <text fg={buy ? theme().success : theme().error} wrapMode="word">
                  {fillDatePrefix(f.ts, prev?.ts)}
                  {hhmm(f.ts)}
                  {(f.side ?? "?").toUpperCase()} {String(f.qty ?? "?")} {f.symbol ?? "?"} @
                  {fmtPrice(f.price)}
                </text>
              )
            }}
          </For>
        </Show>
        <Show when={queued().length > 0}>
          <text fg={theme().textMuted} marginTop={1}>queued (next open) · /cancel by id</text>
          <For each={queued()}>
            {(q) => <text fg={theme().text}>{queuedLine(q)}</text>}
          </For>
        </Show>
        <Show when={events().length > 0}>
          <text fg={theme().textMuted} marginTop={1}>events</text>
          <For each={events()}>
            {(e) => (
              <text fg={theme().text} wrapMode="word">
                {eventLine(e)}
              </text>
            )}
          </For>
        </Show>
        </box>
      </Show>
    </box>
  )
}

const tui: TuiPlugin = async (api) => {
  api.slots.register({
    order: 350,
    slots: {
      sidebar_content() {
        return <View api={api} />
      },
      // F5 option ②: also render the trading panel on the home route, so a fresh launch
      // (no `-c`) shows the live sidebar from the start without resuming a stale session.
      home_sidebar() {
        return <View api={api} />
      },
    },
  })
}

const plugin: InternalTuiPlugin = { id, tui }
export default plugin

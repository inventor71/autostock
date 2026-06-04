import { createSignal, onCleanup, createMemo, Show, For } from "solid-js"
import type { MonitorData, CurrentTurn, MonitorTurn, MonitorDecision, InterventionMarker } from "../types"
import { DEFAULT_MARKET_RULE } from "../types"
import { computeLayout, phaseAt, labelCells, etDateOf, WINDOW_MS, liveWindowStart } from "../utils/timeline-layout"
import type { SessionData } from "../hooks/use-session-data"
import { readSessionData, readHistoricalSession } from "../hooks/use-session-data"
import {
  markerGlyph, markerColor, interventionGlyph, interventionColor, fmtCost,
  phaseLabel, phaseShort, phaseColor, fmtWindowRange, fmtTurnLabel,
} from "../utils/format"

export interface TimelineBarProps {
  width: number
  monitor: () => MonitorData | null
  currentTurn: () => CurrentTurn | null
  onMarkerClick: (turn: MonitorTurn, decisions: MonitorDecision[], x: number, y: number) => void
  onInterventionClick?: (iv: InterventionMarker, x: number, y: number) => void
}

// F25: ET date (America/New_York) for "today" — the default session.
function todayEtDate(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date())
}

export function TimelineBar(props: TimelineBarProps) {
  const [blinkOn, setBlinkOn] = createSignal(true)
  const blinkTimer = setInterval(() => setBlinkOn((v) => !v), 500)
  onCleanup(() => clearInterval(blinkTimer))

  // F45: pinned view-window start (epoch ms). null = auto-follow now (live).
  const [pinnedStart, setPinnedStart] = createSignal<number | null>(null)

  const liveDate = createMemo(() => props.monitor()?.session_et_date ?? todayEtDate())
  const wsRoot = createMemo(() => props.monitor()?.workspace_root ?? null)
  const rule = createMemo(() => props.monitor()?.market ?? DEFAULT_MARKET_RULE)
  const barWidth = createMemo(() => props.width)

  // F45: the live window start that contains `now`, anchored on sessionBounds.winStart.
  const liveStart = createMemo(() => liveWindowStart(Date.now(), liveDate(), rule()))

  const viewStart = () => pinnedStart() ?? liveStart()
  const viewEnd = () => viewStart() + WINDOW_MS
  const isLive = () => pinnedStart() === null
  // F44: the viewed window covers "today" if live or the primary ET date matches today.
  const isToday = () => pinnedStart() === null || primaryEtDate() === liveDate()

  const goPrev = () => setPinnedStart(viewStart() - WINDOW_MS)
  const goNext = () => setPinnedStart(viewStart() + WINDOW_MS)
  const goToday = () => setPinnedStart(null)

  // F45: the ET date at the view-window midpoint — used for sessionBounds (region drawing).
  const primaryEtDate = () => etDateOf((viewStart() + viewEnd()) / 2, rule().tz)

  // F45: load session data from all ET dates the view window covers.
  // In live mode the monitor covers the live date; historical dates read from files.
  const session = createMemo((): SessionData => {
    const vs = viewStart()
    const ve = viewEnd()
    const tz = rule().tz
    const dates = new Set<string>()
    dates.add(etDateOf(vs, tz))
    // Fence-post: when the window edge falls exactly at midnight ET, the tail
    // instant belongs to a different calendar date. Sample 1ms before the edge.
    dates.add(etDateOf(ve - 1, tz))

    const all: SessionData = { turns: [], interventions: [], decisions: [] }
    for (const date of dates) {
      const sd = date === liveDate()
        ? readSessionData(props.monitor(), date)
        : readHistoricalSession(wsRoot(), date)
      all.turns.push(...sd.turns)
      all.interventions.push(...sd.interventions)
      all.decisions.push(...sd.decisions)
    }
    return all
  })

  const layout = createMemo(() =>
    computeLayout({
      turns: session().turns,
      interventions: session().interventions,
      barWidth: barWidth(),
      etDate: primaryEtDate(),
      rule: rule(),
      window: { start: viewStart(), end: viewEnd() },
    }),
  )

  const disconnected = () => props.monitor() === null

  // Current market phase — only meaningful on the live window.
  const phase = () => (isLive() ? phaseAt(layout().bounds, Date.now()) : null)

  // F45: now-label text for the NavRow (e.g. "06-04 20:00 → 06-05 08:00").
  const windowLabel = () => fmtWindowRange(viewStart(), viewEnd())

  // F44: queued count (live session only) for the in-flight turn label's "+N queued".
  const queued = () => (isToday() ? (props.monitor()?.queued ?? 0) : 0)

  return (
    <box width={props.width} height={3} flexDirection="column">
      <Show when={!disconnected()} fallback={<text fg="gray">{"  Monitor disconnected"}</text>}>
        {/* F50: status + date nav on the same row */}
        <NavRow
          label={windowLabel()}
          isLive={isLive()}
          phase={phase()}
          width={props.width}
          todayCost={isLive() ? (props.monitor()?.turns?.today_cost_usd ?? 0) : 0}
          currentTurn={isToday() ? props.currentTurn() : null}
          queued={queued()}
          blinkOn={blinkOn()}
          onPrev={goPrev}
          onNext={goNext}
          onToday={goToday}
        />
        {/* Row 1: tick labels (local time) + now arrow */}
        <TickRow
          layout={layout()}
          width={props.width}
          currentTurn={isLive() ? props.currentTurn() : null}
          blinkOn={blinkOn()}
        />
        {/* Row 2: market regions + markers */}
        <MarkerRow
          layout={layout()}
          width={props.width}
          decisions={session().decisions}
          currentTurn={isLive() ? props.currentTurn() : null}
          blinkOn={blinkOn()}
          onMarkerClick={props.onMarkerClick}
          onInterventionClick={props.onInterventionClick}
        />
      </Show>
    </box>
  )
}

function NavRow(props: {
  label: string
  isLive: boolean
  phase: string | null
  width: number
  todayCost: number
  currentTurn: CurrentTurn | null
  queued: number
  blinkOn: boolean
  onPrev: () => void
  onNext: () => void
  onToday: () => void
}) {
  const displayLabel = () => props.isLive ? `${props.label} (Live)` : props.label
  const turn = () => props.currentTurn
  return (
    <box width={props.width} flexDirection="row" gap={1} paddingLeft={1}>
      {/* F50: status inline — was separate StatusRow above the nav bar */}
      <Show when={turn()} fallback={<text fg="#555555">{"idle"}</text>}>
        {(t) => {
          // Read blinkOn INSIDE the reactive label() scope so the elapsed clock re-renders on
          // every 500ms blink tick. (Reading it in the Show-child body runs once — Date.now() is
          // not reactive, so the timer would freeze.) Mirrors TickRow/MarkerRow's now-cursor blink.
          const label = () => {
            void props.blinkOn
            return fmtTurnLabel(t(), props.queued, Date.now()) ?? ""
          }
          return (
            // flexDirection="row": keep "● " and the label on ONE line. Without it opentui's
            // default column layout stacks them vertically, making NavRow 2 rows tall and
            // overflowing the parent's height={3} (NavRow/TickRow/MarkerRow) — the bar "breaks".
            <box flexDirection="row">
              <text fg={props.blinkOn ? "green" : "#2f6f4f"}>{"● "}</text>
              <text fg="white">{label()}</text>
            </box>
          )
        }}
      </Show>
      <box onMouseUp={(e: any) => { props.onPrev(); e.stopPropagation?.() }}>
        <text fg="cyan">{"[ < ]"}</text>
      </box>
      <text fg="white">{displayLabel()}</text>
      <box onMouseUp={(e: any) => { props.onNext(); e.stopPropagation?.() }}>
        <text fg="cyan">{"[ > ]"}</text>
      </box>
      <Show when={!props.isLive}>
        <box onMouseUp={(e: any) => { props.onToday(); e.stopPropagation?.() }}>
          <text fg="yellow">{"[ Live ]"}</text>
        </box>
      </Show>
      {/* Current market-phase badge — answers "pre-market or regular right now?" */}
      <Show when={props.phase}>
        <text fg={phaseColor(props.phase!)}>{`● ${phaseLabel(props.phase!)}`}</text>
      </Show>
      <Show when={props.isLive}>
        <text fg="gray">{`· ${fmtCost(props.todayCost)}`}</text>
      </Show>
    </box>
  )
}

function TickRow(props: {
  layout: ReturnType<typeof computeLayout>
  width: number
  currentTurn: CurrentTurn | null
  blinkOn: boolean
}) {
  const line = () => {
    const chars = new Array(props.width).fill(" ")
    for (const tick of props.layout.ticks) {
      const lbl = tick.label
      for (let i = 0; i < lbl.length && tick.x + i < props.width; i++) {
        if (tick.x + i >= 0) chars[tick.x + i] = lbl[i]
      }
    }
    return chars.join("")
  }
  const nowX = () => props.layout.nowX
  return (
    <box width={props.width}>
      <text fg="gray">{line()}</text>
      {/* Now marker: a bright downward arrow above the timeline (clearly "now"). */}
      <Show when={nowX() >= 0 && nowX() < props.width}>
        <box position="absolute" left={nowX()} width={1}>
          <text fg={props.currentTurn && props.blinkOn ? "green" : "yellow"}><b>▼</b></text>
        </box>
      </Show>
    </box>
  )
}

// Market-region backgrounds — distinct enough to read on a dark terminal; the
// regular session is the brightest (it's the one that matters most).
const REGION_BG: Record<string, string> = {
  pre: "#26304d",      // dim blue  (pre-market)
  regular: "#1f4d33",  // green     (regular session — brightest)
  after: "#3d2740",    // dim purple (after-hours)
}

function MarkerRow(props: {
  layout: ReturnType<typeof computeLayout>
  width: number
  decisions: MonitorDecision[]
  currentTurn: CurrentTurn | null
  blinkOn: boolean
  onMarkerClick: (turn: MonitorTurn, decisions: MonitorDecision[], x: number, y: number) => void
  onInterventionClick?: (iv: InterventionMarker, x: number, y: number) => void
}) {
  const decisionsFor = (turnId: string) => props.decisions.filter((d) => d.turn_id === turnId)

  // Compose the ENTIRE row into one styled-text line (precedence band < boundary < marker
  // < intervention < now-cursor < label) and render it as a SINGLE <text> of merged spans —
  // the same single-text-node path as TickRow and the band, which the live terminal renderer
  // repaints reliably. The previous per-marker `position:absolute` boxes moved/recreated on
  // every date change, and the live renderer's per-cell damage tracking dropped them, so
  // markers flickered in/out even though the composed buffer was always correct.
  const spans = createMemo(() => {
    const W = props.width
    const lay = props.layout
    const ch: string[] = new Array(W).fill(" ")
    const fg: string[] = new Array(W).fill("gray")
    const bg: (string | undefined)[] = new Array(W).fill(undefined)
    const put = (x: number, c: string, f: string, b?: string) => {
      if (x < 0 || x >= W) return
      ch[x] = c; fg[x] = f; if (b !== undefined) bg[x] = b
    }
    // Region bands (carry each region's bg so the session is identifiable).
    for (const r of lay.regions) {
      if (r.x1 <= r.x0) continue
      for (let x = Math.max(r.x0, 0); x < Math.min(r.x1, W); x++) put(x, "─", phaseColor(r.kind), REGION_BG[r.kind])
    }
    // Market open/close boundaries.
    const reg = lay.regions.find((r) => r.kind === "regular")
    if (reg && reg.x1 > reg.x0) {
      put(reg.x0, "│", "#7faaff", REGION_BG.regular)
      put(reg.x1, "│", "#7faaff", REGION_BG.after)
    }
    // Turn markers (keep the underlying band bg). Off-window → edge arrow.
    for (const mp of lay.markers) {
      const g = mp.offscreen === -1 ? "‹" : mp.offscreen === 1 ? "›" : markerGlyph(mp.turn.type, mp.turn.health)
      put(mp.x, g, markerColor(mp.turn.type, mp.turn.health))
    }
    // Human interventions paint above markers.
    for (const ip of lay.interventions) {
      const g = ip.offscreen === -1 ? "‹" : ip.offscreen === 1 ? "›" : interventionGlyph(ip.intervention.verb)
      put(ip.x, g, interventionColor(ip.intervention.verb))
    }
    // Now cursor (live session only; blinks green during an in-flight turn).
    if (lay.nowX >= 0 && lay.nowX < W) put(lay.nowX, "┃", props.currentTurn && props.blinkOn ? "green" : "yellow")
    // F34: PRE/OPEN/AFT labels are the TOPMOST layer (override glyph+fg, keep band bg).
    for (const lc of labelCells(lay.regions, W, phaseShort)) put(lc.x, lc.ch, phaseColor(lc.kind))

    // Merge consecutive same-style cells into runs (fewer spans).
    const runs: { text: string; fg: string; bg?: string }[] = []
    for (let x = 0; x < W; x++) {
      const last = runs[runs.length - 1]
      if (last && last.fg === fg[x] && last.bg === bg[x]) last.text += ch[x]
      else runs.push({ text: ch[x]!, fg: fg[x]!, bg: bg[x] })
    }
    return runs
  })

  // One hit-test for the whole row: map the clicked column to the marker/intervention there
  // (interventions win on a tie, matching the paint order). Replaces the per-box handlers + the
  // F34 label click-forwarding. ASSUMPTION: this row starts at screen column 0, so the mouse
  // event's absolute x equals the timeline column. That holds today (the bar is full-width with
  // no left gutter), but if a left margin/sidebar/border is ever added around this row, subtract
  // the row's screen origin here — otherwise every click maps to the wrong column.
  // Off-window markers are clamped to x=0/width-1; if several share an edge cell only the
  // topmost (last-painted) opens, consistent with the paint.
  type Hit = { kind: "iv"; iv: InterventionMarker } | { kind: "turn"; turn: MonitorTurn }
  const entityAt = (x: number): Hit | null => {
    for (let i = props.layout.interventions.length - 1; i >= 0; i--) {
      const ip = props.layout.interventions[i]!
      if (ip.x === x) return { kind: "iv", iv: ip.intervention }
    }
    for (let i = props.layout.markers.length - 1; i >= 0; i--) {
      const mp = props.layout.markers[i]!
      if (mp.x === x) return { kind: "turn", turn: mp.turn }
    }
    return null
  }

  return (
    <box
      width={props.width}
      onMouseUp={(evt: any) => {
        const x = evt.x ?? -1
        const hit = entityAt(x)
        if (hit?.kind === "iv") { props.onInterventionClick?.(hit.iv, x, 3); evt.stopPropagation?.() }
        else if (hit?.kind === "turn") { props.onMarkerClick(hit.turn, decisionsFor(hit.turn.id), x, 3); evt.stopPropagation?.() }
      }}
    >
      <text>
        <For each={spans()}>
          {(s) => <span style={s.bg !== undefined ? { fg: s.fg, bg: s.bg } : { fg: s.fg }}>{s.text}</span>}
        </For>
      </text>
    </box>
  )
}

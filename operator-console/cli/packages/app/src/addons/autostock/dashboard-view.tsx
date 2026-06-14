// F79 C6 — DashboardView (FR-2/FR-7/FR-8/NFR-7 UI). Presentational binding to the tested
// SnapshotController model (toDashboard). Renders equity / day P&L / positions / health /
// pending-approval badge / asOf, with offline + stale signals. Health glyph and position
// chips are tappable (FR-7 detail parity); pull-to-refresh + auto-poll feed `model` from
// the shell. Plain elements + tailwind; logic lives in the tested core.

import { For, Show } from "solid-js"
import type { DashboardModel } from "./dashboard"

export type DashboardViewProps = {
  model: DashboardModel
  /** NFR-7: snapshot is older than the freshness threshold. */
  stale?: boolean
  /** FR-8 pull-to-refresh / manual refresh. */
  onRefresh?: () => void
  /** FR-7: open the 9-dim health overlay. */
  onOpenHealth?: () => void
  /** FR-7: open a position's thesis. */
  onOpenPosition?: (symbol: string) => void
}

function fmtMoney(v: number | null): string {
  return v === null ? "—" : `$${v.toLocaleString()}`
}

function fmtPct(v: number | null): string {
  return v === null ? "" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`
}

function healthGlyph(ok: boolean | null): string {
  return ok === null ? "?" : ok ? "●" : "✗"
}

export function DashboardView(props: DashboardViewProps) {
  const m = () => props.model
  return (
    <div class="flex flex-col gap-4 p-4">
      <Show when={m().offline}>
        <div class="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text-weak">
          오프라인 — 서버에 연결되지 않음
        </div>
      </Show>

      <div class="flex items-baseline justify-between">
        <div class="flex flex-col">
          <span class="text-2xl font-semibold text-text">{fmtMoney(m().equity)}</span>
          <span
            class="text-sm"
            classList={{
              "text-text-success": (m().dayPnlPct ?? 0) >= 0,
              "text-text-danger": (m().dayPnlPct ?? 0) < 0,
            }}
          >
            {fmtPct(m().dayPnlPct)}
          </span>
        </div>
        <div class="flex items-center gap-3">
          <Show when={(m().pendingApprovals ?? 0) > 0}>
            <span class="rounded-full bg-primary px-2 py-0.5 text-xs font-medium text-text-invert">
              승인대기 {m().pendingApprovals}
            </span>
          </Show>
          <button
            type="button"
            class="text-lg"
            aria-label="건강 상세"
            onClick={() => props.onOpenHealth?.()}
          >
            {healthGlyph(m().healthOk)}
          </button>
        </div>
      </div>

      <div class="flex flex-col gap-2">
        <span class="text-xs uppercase tracking-wide text-text-weak">포지션 {m().positionCount}</span>
        <Show
          when={m().symbols.length > 0}
          fallback={<span class="text-sm text-text-weak">보유 포지션 없음</span>}
        >
          <div class="flex flex-wrap gap-2">
            <For each={m().symbols}>
              {(sym) => (
                <button
                  type="button"
                  class="rounded-md border border-border px-2 py-1 text-sm text-text"
                  onClick={() => props.onOpenPosition?.(sym)}
                >
                  {sym}
                </button>
              )}
            </For>
          </div>
        </Show>
      </div>

      <div class="flex items-center justify-between text-xs text-text-weak">
        <span>
          <Show when={props.stale} fallback={<>{m().asOf ? `갱신 ${m().asOf}` : ""}</>}>
            <span class="text-text-danger">오래된 데이터 — 갱신 중…</span>
          </Show>
        </span>
        <button type="button" class="rounded-md border border-border px-2 py-1" onClick={() => props.onRefresh?.()}>
          새로고침
        </button>
      </div>
    </div>
  )
}

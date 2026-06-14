// F79 C6 — DashboardView (FR-2/FR-7/FR-8/NFR-7). Presentational binding to the tested
// SnapshotController model (toDashboard). Trading-terminal hierarchy: the equity figure is
// the hero (large tabular-nums), labels are quiet uppercase, positions/health/pending sit in
// hairline raised cards. Health glyph + position chips are tappable (FR-7); pull-to-refresh
// + poll feed `model` from the shell. Tokens are the host opencode system — no new palette.

import { For, Show } from "solid-js"
import type { DashboardModel } from "./dashboard"

export type DashboardViewProps = {
  model: DashboardModel
  /** NFR-7: snapshot older than the freshness threshold. */
  stale?: boolean
  /** FR-8 pull-to-refresh / manual refresh. */
  onRefresh?: () => void
  /** FR-7: open the 9-dim health overlay. */
  onOpenHealth?: () => void
  /** FR-7: open a position's thesis. */
  onOpenPosition?: (symbol: string) => void
}

function fmtMoney(v: number | null): string {
  return v === null ? "—" : v.toLocaleString(undefined, { style: "currency", currency: "USD" })
}
function fmtPct(v: number | null): string {
  return v === null ? "—" : `${v >= 0 ? "▲" : "▼"} ${Math.abs(v).toFixed(2)}%`
}

export function DashboardView(props: DashboardViewProps) {
  const m = () => props.model
  const up = () => (m().dayPnlPct ?? 0) >= 0

  return (
    <div class="flex min-h-full flex-col gap-3 bg-background-base p-4">
      <Show when={m().offline}>
        <div class="flex items-center gap-2 rounded-md border border-border-base bg-surface-base px-3 py-2 text-sm text-text-weak">
          <span class="size-2 rounded-full bg-border-weak-base" />
          오프라인 — 서버에 연결되지 않음
        </div>
      </Show>

      {/* Hero — equity + day P&L */}
      <section class="rounded-xl border border-border-weak-base bg-surface-raised-base p-5 shadow-xs-border-base">
        <p class="text-xs uppercase tracking-wide text-text-faint">총 자산</p>
        <p class="mt-1 text-3xl font-semibold tabular-nums text-text-strong">{fmtMoney(m().equity)}</p>
        <p
          class="mt-1 text-sm font-medium tabular-nums"
          classList={{ "text-icon-success-base": up(), "text-icon-critical-base": !up() }}
        >
          {fmtPct(m().dayPnlPct)}
          <span class="ml-1 text-text-faint">오늘</span>
        </p>
      </section>

      {/* Status row — pending approvals + health */}
      <section class="grid grid-cols-2 gap-3">
        <button
          type="button"
          class="flex flex-col items-start rounded-xl border border-border-weak-base bg-surface-raised-base p-4 text-left shadow-xs-border-base transition active:scale-[0.98]"
          onClick={() => props.onOpenHealth?.()}
        >
          <span class="text-xs uppercase tracking-wide text-text-faint">시스템 건강</span>
          <span class="mt-1 flex items-center gap-2">
            <span
              class="size-2.5 rounded-full"
              classList={{
                "bg-icon-success-base": m().healthOk === true,
                "bg-icon-critical-base": m().healthOk === false,
                "bg-border-weak-base": m().healthOk === null,
              }}
            />
            <span class="text-base font-medium text-text-strong">
              {m().healthOk === null ? "—" : m().healthOk ? "정상" : "점검"}
            </span>
          </span>
        </button>

        <div
          class="flex flex-col items-start rounded-xl border p-4 shadow-xs-border-base"
          classList={{
            "border-border-weak-base bg-surface-raised-base": (m().pendingApprovals ?? 0) === 0,
            "border-border-base bg-surface-raised-base": (m().pendingApprovals ?? 0) > 0,
          }}
        >
          <span class="text-xs uppercase tracking-wide text-text-faint">승인 대기</span>
          <span class="mt-1 flex items-center gap-2">
            <Show
              when={(m().pendingApprovals ?? 0) > 0}
              fallback={<span class="text-base font-medium text-text-weak">없음</span>}
            >
              <span class="inline-flex min-w-6 animate-pulse items-center justify-center rounded-full bg-icon-interactive-base px-2 py-0.5 text-sm font-semibold tabular-nums text-text-invert-base">
                {m().pendingApprovals}
              </span>
              <span class="text-sm text-text-weak">처리 필요</span>
            </Show>
          </span>
        </div>
      </section>

      {/* Positions */}
      <section class="rounded-xl border border-border-weak-base bg-surface-raised-base p-4 shadow-xs-border-base">
        <div class="flex items-baseline justify-between">
          <span class="text-xs uppercase tracking-wide text-text-faint">포지션</span>
          <span class="text-sm font-medium tabular-nums text-text-weak">{m().positionCount}</span>
        </div>
        <Show
          when={m().symbols.length > 0}
          fallback={<p class="mt-3 text-sm text-text-weak">보유 포지션 없음</p>}
        >
          <div class="mt-3 flex flex-wrap gap-2">
            <For each={m().symbols}>
              {(sym) => (
                <button
                  type="button"
                  class="rounded-md border border-border-weak-base bg-surface-base px-3 py-1.5 text-sm font-medium text-text-strong transition active:scale-95 hover:bg-surface-raised-base-hover"
                  onClick={() => props.onOpenPosition?.(sym)}
                >
                  {sym}
                </button>
              )}
            </For>
          </div>
        </Show>
      </section>

      {/* Footer — freshness + refresh */}
      <div class="mt-auto flex items-center justify-between pt-1 text-xs text-text-faint">
        <Show
          when={props.stale}
          fallback={<span class="tabular-nums">{m().asOf ? `갱신 ${m().asOf}` : ""}</span>}
        >
          <span class="flex items-center gap-1.5 text-icon-critical-base">
            <span class="size-1.5 animate-pulse rounded-full bg-icon-critical-base" />
            오래된 데이터 — 갱신 중
          </span>
        </Show>
        <button
          type="button"
          class="rounded-md border border-border-weak-base px-3 py-1.5 font-medium text-text-weak transition active:scale-95 hover:bg-surface-raised-base-hover"
          onClick={() => props.onRefresh?.()}
        >
          새로고침
        </button>
      </div>
    </div>
  )
}

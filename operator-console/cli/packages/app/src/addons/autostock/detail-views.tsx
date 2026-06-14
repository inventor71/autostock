// F79 C7 — DetailViews (FR-7, read-only parity with the TUI). PositionThesisView shows a
// held position's thesis (F53 parity); HealthOverlay shows the 9-dimension health snapshot
// (F69 parity). Both are read paths — no signature required (F75 topology). Presentational:
// the shell fetches via steer_read and passes data in. Host opencode tokens.

import { For, Show } from "solid-js"

function OverlayShell(props: { title: string; onClose: () => void; children: unknown }) {
  return (
    <div class="fixed inset-0 z-50 flex flex-col bg-background-base">
      <header class="flex items-center justify-between border-b border-border-weak-base px-4 py-3">
        <span class="text-base font-semibold text-text-strong">{props.title}</span>
        <button
          type="button"
          class="h-9 rounded-md border border-border-weak-base px-3 text-sm font-medium text-text-weak transition active:scale-95"
          onClick={() => props.onClose()}
        >
          닫기
        </button>
      </header>
      <div class="flex-1 overflow-auto p-4">{props.children as never}</div>
    </div>
  )
}

export type PositionThesisProps = {
  symbol: string
  /** thesis text (steer_read), or null while loading / when none exists. */
  thesis: string | null
  loading?: boolean
  onClose: () => void
}

export function PositionThesisView(props: PositionThesisProps) {
  return (
    <OverlayShell title={`${props.symbol} · Thesis`} onClose={props.onClose}>
      <Show when={!props.loading} fallback={<p class="text-sm text-text-weak">불러오는 중…</p>}>
        <Show
          when={props.thesis}
          fallback={<p class="text-sm text-text-weak">기록된 thesis가 없습니다.</p>}
        >
          <article class="rounded-xl border border-border-weak-base bg-surface-raised-base p-4 text-sm leading-relaxed text-text-base shadow-xs-border-base">
            <pre class="whitespace-pre-wrap font-sans">{props.thesis}</pre>
          </article>
        </Show>
      </Show>
    </OverlayShell>
  )
}

export type HealthDimension = { name: string; ok: boolean; detail?: string }

export type HealthOverlayProps = {
  /** overall summary line (e.g. "All checks passed."). */
  summary: string | null
  dimensions: HealthDimension[]
  loading?: boolean
  onClose: () => void
}

export function HealthOverlay(props: HealthOverlayProps) {
  return (
    <OverlayShell title="시스템 건강" onClose={props.onClose}>
      <Show when={!props.loading} fallback={<p class="text-sm text-text-weak">불러오는 중…</p>}>
        <Show when={props.summary}>
          <p class="mb-3 text-sm text-text-weak">{props.summary}</p>
        </Show>
        <div class="flex flex-col gap-2">
          <For each={props.dimensions}>
            {(d) => (
              <div class="flex items-start gap-3 rounded-xl border border-border-weak-base bg-surface-raised-base p-3 shadow-xs-border-base">
                <span
                  class="mt-1 size-2.5 shrink-0 rounded-full"
                  classList={{ "bg-icon-success-base": d.ok, "bg-icon-critical-base": !d.ok }}
                />
                <div class="flex min-w-0 flex-col">
                  <span class="text-sm font-medium text-text-strong">{d.name}</span>
                  <Show when={!d.ok && d.detail}>
                    <span class="text-xs text-text-weak">{d.detail}</span>
                  </Show>
                </div>
              </div>
            )}
          </For>
        </div>
      </Show>
    </OverlayShell>
  )
}

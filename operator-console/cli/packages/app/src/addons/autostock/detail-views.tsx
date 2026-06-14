// F79 C7 — DetailViews (FR-7, read-only parity with the TUI). PositionThesisView shows a
// held position's thesis (F53 parity); HealthOverlay shows the 9-dimension health snapshot
// (F69 parity). Both are read paths — no signature required (F75 topology). Presentational:
// the shell fetches via steer_read and passes data in; these render + own dismiss UX.

import { For, Show } from "solid-js"

export type PositionThesisProps = {
  symbol: string
  /** thesis text (steer_read), or null while loading / when none exists. */
  thesis: string | null
  loading?: boolean
  onClose: () => void
}

export function PositionThesisView(props: PositionThesisProps) {
  return (
    <div class="fixed inset-0 z-50 flex flex-col bg-surface p-4">
      <div class="flex items-center justify-between">
        <span class="text-base font-semibold text-text">{props.symbol} — Thesis</span>
        <button type="button" class="text-sm text-text-weak" onClick={() => props.onClose()}>
          닫기
        </button>
      </div>
      <div class="mt-3 flex-1 overflow-auto text-sm text-text">
        <Show when={!props.loading} fallback={<span class="text-text-weak">불러오는 중…</span>}>
          <Show when={props.thesis} fallback={<span class="text-text-weak">기록된 thesis가 없습니다.</span>}>
            <pre class="whitespace-pre-wrap font-sans">{props.thesis}</pre>
          </Show>
        </Show>
      </div>
    </div>
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
    <div class="fixed inset-0 z-50 flex flex-col bg-surface p-4">
      <div class="flex items-center justify-between">
        <span class="text-base font-semibold text-text">시스템 건강</span>
        <button type="button" class="text-sm text-text-weak" onClick={() => props.onClose()}>
          닫기
        </button>
      </div>
      <Show when={!props.loading} fallback={<span class="mt-3 text-text-weak">불러오는 중…</span>}>
        <Show when={props.summary}>
          <span class="mt-2 text-sm text-text-weak">{props.summary}</span>
        </Show>
        <div class="mt-3 flex flex-1 flex-col gap-2 overflow-auto">
          <For each={props.dimensions}>
            {(d) => (
              <div class="flex items-start gap-2 rounded-md border border-border px-3 py-2">
                <span classList={{ "text-text-success": d.ok, "text-text-danger": !d.ok }}>
                  {d.ok ? "●" : "✗"}
                </span>
                <div class="flex flex-col">
                  <span class="text-sm text-text">{d.name}</span>
                  <Show when={!d.ok && d.detail}>
                    <span class="text-xs text-text-weak">{d.detail}</span>
                  </Show>
                </div>
              </div>
            )}
          </For>
        </div>
      </Show>
    </div>
  )
}

// F79 C5 — ConfirmSheet (FR-3 UI). Presentational bottom sheet: the shell passes the pending
// approval + injected handlers (onApprove -> permission.respondSigned, onReject -> plain
// reject). Owns busy/error UX and renders WebAuthn failure reasons in Korean. Approve runs the
// passkey ceremony; cancel/lock/error keep the action un-sent (fail-closed) and surface a
// reason. Reject needs no signature (F75 topology). Host opencode tokens — no new palette.

import { createSignal, Show } from "solid-js"
import type { PendingApproval } from "./approval-queue"
import { LockedError, WebAuthnError } from "./signed-mutation"

export type ConfirmSheetProps = {
  request: PendingApproval | null
  /** Runs the WebAuthn ceremony + signed single-use reply. Throws on cancel/lock/error
   *  (fail-closed). Single-use only — no "always" (a persistent allow rule would bypass the
   *  passkey gate for future mutations). */
  onApprove: () => Promise<void>
  /** Reject — no signature required. */
  onReject: () => Promise<void> | void
  /** Called after a successful approve or a reject, to dismiss + advance the queue. */
  onClose?: () => void
}

export function ConfirmSheet(props: ConfirmSheetProps) {
  const [busy, setBusy] = createSignal(false)
  const [error, setError] = createSignal<string | null>(null)

  async function approve() {
    setError(null)
    setBusy(true)
    try {
      await props.onApprove()
      props.onClose?.()
    } catch (e) {
      if (e instanceof LockedError) setError("화면이 잠겨 있습니다 — 재인증 후 다시 시도하세요.")
      else if (e instanceof WebAuthnError) setError(e.message || "패스키 서명에 실패했습니다.")
      else setError("승인에 실패했습니다. 잠시 후 다시 시도하세요.")
    } finally {
      setBusy(false)
    }
  }

  async function reject() {
    setError(null)
    setBusy(true)
    try {
      await props.onReject()
      props.onClose?.()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Show when={props.request}>
      {(req) => (
        <div class="fixed inset-0 z-50 flex flex-col justify-end">
          {/* scrim */}
          <div class="absolute inset-0 bg-background-base/70 backdrop-blur-sm" />
          {/* sheet */}
          <div class="relative animate-in slide-in-from-bottom rounded-t-2xl border-t border-border-base bg-surface-raised-base p-5 pb-8 shadow-lg-border-base">
            <div class="mx-auto flex max-w-md flex-col gap-4">
              <div class="mx-auto h-1 w-10 rounded-full bg-border-base" />

              <div class="flex items-start gap-3">
                <span class="mt-1 size-3 shrink-0 rounded-full bg-icon-interactive-base" />
                <div class="flex min-w-0 flex-col gap-0.5">
                  <span class="text-base font-semibold text-text-strong">승인 요청</span>
                  <span class="truncate text-sm text-text-weak">{req().title ?? req().permission ?? req().id}</span>
                  <span class="text-xs text-text-faint">패스키 지문 서명이 필요한 작업입니다.</span>
                </div>
              </div>

              <Show when={error()}>
                <div class="rounded-md border border-border-base bg-surface-base px-3 py-2 text-xs text-icon-critical-base">
                  {error()}
                </div>
              </Show>

              {/* Only single-use approval — every mutating action requires a fresh passkey.
                  No "always": a persistent allow rule would let future trades execute
                  server-side without a signature, defeating the F75/F79 gate. */}
              <div class="flex flex-col gap-2">
                <button
                  type="button"
                  class="flex h-12 items-center justify-center rounded-xl bg-icon-interactive-base text-base font-semibold text-text-invert-base transition active:scale-[0.98] disabled:opacity-50"
                  disabled={busy()}
                  onClick={() => approve()}
                >
                  {busy() ? "처리 중…" : "승인 — 지문 서명"}
                </button>
                <button
                  type="button"
                  class="h-11 rounded-xl border border-border-base text-sm font-medium text-text-weak transition active:scale-[0.98] disabled:opacity-50"
                  disabled={busy()}
                  onClick={reject}
                >
                  거절
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </Show>
  )
}

// F79 C5 — ConfirmSheet (FR-3 UI). Presentational: the shell passes the pending approval
// and injected handlers (onApprove -> permission.respondSigned, onReject -> plain reject).
// This component owns only busy/error UX and renders the WebAuthn failure reasons in Korean.
// Approve runs the passkey ceremony (via onApprove); cancel/lock/error keep the action
// un-sent (fail-closed) and surface a reason. Reject needs no signature (F75 topology).
//
// Plain elements + tailwind so it restyles cleanly once seen on a real phone; behavior is
// fully covered by the tested cores (signed-mutation, approval-queue).

import { createSignal, Show } from "solid-js"
import type { PendingApproval } from "./approval-queue"
import { LockedError, WebAuthnError } from "./signed-mutation"

export type ConfirmSheetProps = {
  request: PendingApproval | null
  /** Runs the WebAuthn ceremony + signed reply. Throws on cancel/lock/error (fail-closed). */
  onApprove: (response: "once" | "always") => Promise<void>
  /** Reject — no signature required. */
  onReject: () => Promise<void> | void
  /** Called after a successful approve or a reject, to dismiss + advance the queue. */
  onClose?: () => void
}

export function ConfirmSheet(props: ConfirmSheetProps) {
  const [busy, setBusy] = createSignal(false)
  const [error, setError] = createSignal<string | null>(null)

  async function approve(response: "once" | "always") {
    setError(null)
    setBusy(true)
    try {
      await props.onApprove(response)
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
        <div class="fixed inset-x-0 bottom-0 z-50 border-t border-border bg-surface p-4 pb-6 shadow-lg">
          <div class="mx-auto flex max-w-md flex-col gap-3">
            <div class="flex flex-col gap-1">
              <span class="text-sm font-semibold text-text">승인 요청</span>
              <span class="text-sm text-text-weak">{req().title ?? req().permission ?? req().id}</span>
              <span class="text-xs text-text-weak">패스키 서명이 필요한 작업입니다.</span>
            </div>

            <Show when={error()}>
              <span class="text-xs text-text-danger">{error()}</span>
            </Show>

            <div class="flex gap-2">
              <button
                type="button"
                class="flex-1 rounded-md bg-primary px-3 py-2 text-sm font-medium text-text-invert disabled:opacity-50"
                disabled={busy()}
                onClick={() => approve("once")}
              >
                {busy() ? "처리 중…" : "승인 (지문)"}
              </button>
              <button
                type="button"
                class="rounded-md border border-border px-3 py-2 text-sm text-text disabled:opacity-50"
                disabled={busy()}
                onClick={() => approve("always")}
              >
                항상 허용
              </button>
              <button
                type="button"
                class="rounded-md border border-border px-3 py-2 text-sm text-text-weak disabled:opacity-50"
                disabled={busy()}
                onClick={reject}
              >
                거절
              </button>
            </div>
          </div>
        </div>
      )}
    </Show>
  )
}

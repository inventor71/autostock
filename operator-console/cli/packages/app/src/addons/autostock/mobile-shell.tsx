// F79 C10 — MobileShell: the PWA home that composes the autostock operator surface for a
// phone. Wires the tested cores to live opencode contexts:
//   - permission.asked / .replied events  → ApprovalQueueController → ConfirmSheet
//   - approve → usePermission().respondSigned (passkey-signed, FR-3)
//   - reject  → usePermission().respond (no signature, F75 topology)
//   - inactivity → LockController curtain, unlocked by a passkey assertion (NFR-6)
//   - DashboardView renders; its LIVE data source (account/positions/health/portfolio) is a
//     follow-up (no mobile read endpoint yet — F83 catalog defers mobile). Graceful until then.
//
// Mounted at /autostock (see app.tsx). Behavior-critical pieces are the tested cores; this
// file is the live composition — verify the round-trip on a real device (post-merge-guide).

import { createSignal, createMemo, For, onCleanup, onMount, Show } from "solid-js"
import { createStore, produce } from "solid-js/store"
import type { PermissionRequest } from "@opencode-ai/sdk/v2/client"
import { useServerSDK } from "@/context/server-sdk"
import { usePermission } from "@/context/permission"
import { useServer } from "@/context/server"
import { DashboardView } from "./dashboard-view"
import { ConfirmSheet } from "./confirm-sheet"
import { badgeCount, nextForSheet, type PendingApproval } from "./approval-queue"
import { DEFAULT_LOCK_TIMEOUT_MS, shouldLock } from "./lock"
import { withWebAuthn } from "./signed-mutation"
import { browserCredentialsGet, serverFetcher } from "./webauthn-fetch"
import { toDashboard } from "./dashboard"

const EMPTY_MODEL = toDashboard(null, { offline: false })

/** Only autostock tools prompt for approval here; read tools are auto-allowed upstream. */
function isAutostockAsk(permission: string): boolean {
  return permission.startsWith("autostock_")
}
function titleOf(req: PermissionRequest): string {
  const t = (req.metadata as { title?: unknown })?.title
  return typeof t === "string" ? t : req.permission
}

export default function MobileShell() {
  const sdk = useServerSDK()
  const permission = usePermission()
  const server = useServer()

  // --- live pending-approval queue (from permission events) -----------------
  const [asks, setAsks] = createStore<Record<string, PermissionRequest>>({})
  const [dismissed, setDismissed] = createSignal<ReadonlySet<string>>(new Set())

  onMount(() => {
    const unsub = sdk.event.listen((e) => {
      const ev = e.details
      if (ev?.type === "permission.asked") {
        const req = ev.properties
        if (!isAutostockAsk(req.permission)) return
        setAsks(produce((d) => void (d[req.id] = req)))
      } else if (ev?.type === "permission.replied") {
        // EventPermissionReplied.properties = { sessionID, requestID, reply } — keyed by
        // requestID, not id. Removes the ask when it is resolved anywhere (here, desktop,
        // auto-accept) so the sheet never shows a phantom already-resolved approval.
        const id = ev.properties.requestID
        if (id) setAsks(produce((d) => void delete d[id]))
      }
    })
    onCleanup(unsub)
  })

  const pendingList = createMemo<PendingApproval[]>(() =>
    Object.values(asks).map((r) => ({ id: r.id, permission: r.permission, title: titleOf(r) })),
  )
  const badge = createMemo(() => badgeCount(pendingList(), dismissed()))
  const current = createMemo(() => nextForSheet(pendingList(), dismissed()))
  const currentReq = createMemo(() => {
    const c = current()
    return c ? asks[c.id] : undefined
  })

  function dismiss(id: string) {
    setDismissed((s) => new Set(s).add(id))
    setAsks(produce((d) => void delete d[id]))
  }

  async function approve() {
    const req = currentReq()
    if (!req) return
    // Single-use only — never "always" (a persistent allow rule would let future mutations
    // run server-side without a passkey, defeating the gate).
    await permission.respondSigned(req, "once") // throws on cancel/lock → ConfirmSheet shows reason
    dismiss(req.id)
  }
  function reject() {
    const req = currentReq()
    if (!req) return
    permission.respond({ sessionID: req.sessionID, permissionID: req.id, response: "reject" })
    dismiss(req.id)
  }

  // --- client-only inactivity lock (NFR-6), unlocked by a passkey assertion ---
  const [locked, setLocked] = createSignal(false)
  const [lastActivity, setLastActivity] = createSignal(Date.now())
  const [unlockError, setUnlockError] = createSignal<string | null>(null)
  const touch = () => setLastActivity(Date.now())

  onMount(() => {
    // Real interaction resets the idle timer — NOT visibilitychange (backgrounding the PWA
    // must not count as activity, or cycling background/foreground would defer the lock
    // forever, NFR-6).
    for (const ev of ["pointerdown", "keydown"] as const) {
      window.addEventListener(ev, touch, { passive: true })
      onCleanup(() => window.removeEventListener(ev, touch))
    }
    // On returning to the foreground, lock immediately if idle exceeded while hidden.
    const onVisible = () => {
      if (document.visibilityState === "visible" && shouldLock(lastActivity(), Date.now(), DEFAULT_LOCK_TIMEOUT_MS)) {
        setLocked(true)
      }
    }
    document.addEventListener("visibilitychange", onVisible)
    onCleanup(() => document.removeEventListener("visibilitychange", onVisible))
    const timer = setInterval(() => {
      if (!locked() && shouldLock(lastActivity(), Date.now(), DEFAULT_LOCK_TIMEOUT_MS)) setLocked(true)
    }, 15_000)
    onCleanup(() => clearInterval(timer))
  })

  function http() {
    const c = server.current
    return c && "http" in c ? c.http : undefined
  }
  async function unlock() {
    setUnlockError(null)
    const h = http()
    if (!h) {
      setLocked(false)
      return
    }
    try {
      // Prove presence with a passkey assertion (reuses the C3 ceremony, no mutation sent).
      await withWebAuthn({ fetcher: serverFetcher(h), credentialsGet: browserCredentialsGet() }, async () => {})
      setLocked(false)
      touch()
    } catch (e) {
      setUnlockError("잠금 해제 실패 — 패스키 인증이 필요합니다.")
    }
  }

  return (
    <div class="relative min-h-full bg-background-base">
      {/* Header */}
      <header class="flex items-center justify-between border-b border-border-weak-base px-4 py-3">
        <span class="text-base font-semibold text-text-strong">autostock</span>
        <span class="flex items-center gap-3">
          <Show when={badge() > 0}>
            <span class="inline-flex min-w-5 items-center justify-center rounded-full bg-icon-interactive-base px-1.5 text-xs font-semibold tabular-nums text-text-invert-base">
              {badge()}
            </span>
          </Show>
          {/* Session deep-link needs a dir+session id (live data = follow-up); home picker for now. */}
          <a href="/" class="text-sm font-medium text-text-weak transition active:scale-95">
            세션 ›
          </a>
        </span>
      </header>

      {/* Dashboard (live data source = follow-up) */}
      <DashboardView model={EMPTY_MODEL} onRefresh={touch} />
      <p class="px-4 pb-4 text-center text-xs text-text-faint">실시간 데이터 연결은 후속 — 승인·세션은 동작합니다.</p>

      {/* Approval sheet (live) */}
      <ConfirmSheet request={current()} onApprove={approve} onReject={reject} onClose={() => {}} />

      {/* Lock curtain (NFR-6) */}
      <Show when={locked()}>
        <div class="fixed inset-0 z-[60] flex flex-col items-center justify-center gap-4 bg-background-base/95 backdrop-blur-sm">
          <span class="text-base font-semibold text-text-strong">화면이 잠겼습니다</span>
          <span class="text-sm text-text-weak">비활성으로 잠금 — 패스키로 해제</span>
          <Show when={unlockError()}>
            <span class="text-xs text-text-danger">{unlockError()}</span>
          </Show>
          <button
            type="button"
            class="flex h-12 items-center justify-center rounded-xl bg-icon-interactive-base px-6 text-base font-semibold text-text-invert-base transition active:scale-[0.98]"
            onClick={unlock}
          >
            잠금 해제 — 지문
          </button>
        </div>
      </Show>
    </div>
  )
}

// F79 C4 — ApprovalQueueController core (FR-6). Pure queue reduction over the pending
// permission asks the app already streams (context/permission + server-sync). The SolidJS
// shell binds badgeCount() for the badge and nextForSheet() to auto-open the ConfirmSheet
// (C5); multiple pending asks are handled one at a time, in arrival order. The server F75
// challenge store is value-keyed (concurrency-safe), so sequential client handling is fine.
//
// We intentionally do NOT re-classify mutating-vs-read on the client (that lives server-side
// in webauthn.ts and could drift) — a permission ASK only fires for tools that need approval,
// so every pending ask is something the operator must act on.

export type PendingApproval = {
  id: string
  /** tool/permission key, when present (purely for display). */
  permission?: string
  /** short human title for the sheet, when the source provides one. */
  title?: string
}

/** Pending asks not yet acted on (dismissed = ids already approved/rejected this session). */
export function selectPending(items: readonly PendingApproval[], dismissed: ReadonlySet<string>): PendingApproval[] {
  const seen = new Set<string>()
  const out: PendingApproval[] = []
  for (const it of items) {
    if (!it?.id) continue
    if (dismissed.has(it.id)) continue
    if (seen.has(it.id)) continue // de-dup repeated ids in the stream snapshot
    seen.add(it.id)
    out.push(it)
  }
  return out
}

/** Badge count = number of distinct pending asks awaiting action. */
export function badgeCount(items: readonly PendingApproval[], dismissed: ReadonlySet<string>): number {
  return selectPending(items, dismissed).length
}

/** The next ask to surface in the sheet (arrival order), or null when the queue is empty. */
export function nextForSheet(
  items: readonly PendingApproval[],
  dismissed: ReadonlySet<string>,
): PendingApproval | null {
  return selectPending(items, dismissed)[0] ?? null
}

// F79 C3 — SignedMutationGateway: the single chokepoint that attaches an
// `x-autostock-webauthn` assertion to every REMOTE mutating call (permission approval
// FR-3, session input FR-4). The server (F75 gate, + F79 S1 for session.prompt) is the
// final authority; this layer only *attaches* a fresh signature and never invents a
// no-signature bypass for mutating actions.
//
// SDK-agnostic by design: the caller supplies a `call(headers)` thunk that performs the
// actual typed SDK request with the headers merged in (the SDK's per-call `headers`
// option, confirmed in sdk/.../core/types.gen.ts). That keeps this module pure and
// unit-testable, and keeps the one place that knows the header name auditable.
//
// Fail-closed (SECURITY-15): if the screen is locked (NFR-6) or the passkey ceremony is
// cancelled/errors, `call` is NEVER invoked — the mutating action does not go through.

import { obtainAssertionHeader, WebAuthnError, type CredentialsGet, type Fetcher } from "./webauthn-client"

export const WEBAUTHN_HEADER = "x-autostock-webauthn"

/** Raised when a mutating action is attempted while the client is locked (NFR-6). */
export class LockedError extends Error {
  constructor(message = "화면이 잠겨 있습니다 — 재인증이 필요합니다") {
    super(message)
    this.name = "LockedError"
  }
}

export type SignedMutationDeps = {
  fetcher: Fetcher
  credentialsGet: CredentialsGet
  /** Optional client-lock probe (NFR-6, client-only lock). True => refuse before signing. */
  isLocked?: () => boolean
}

/**
 * Run the WebAuthn assertion ceremony and hand the resulting signed header to `call`.
 * `call` receives a header bag to merge into the SDK request options. Throws
 * `LockedError` (locked) or `WebAuthnError` (cancelled / assert-options failure) WITHOUT
 * invoking `call` — fail-closed.
 */
export async function withWebAuthn(
  deps: SignedMutationDeps,
  call: (headers: Record<string, string>) => Promise<void>,
): Promise<void> {
  if (deps.isLocked?.()) throw new LockedError()
  const header = await obtainAssertionHeader({ fetcher: deps.fetcher, credentialsGet: deps.credentialsGet })
  await call({ [WEBAUTHN_HEADER]: header })
}

export { WebAuthnError }

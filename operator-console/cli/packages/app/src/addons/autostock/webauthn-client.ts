// F71 U3 — WebAuthn confirm ceremony for mutating approvals (US-5, pairs with U2 server gate).
//
// Flow: server emits a permission ask → the operator taps Approve → we run a passkey
// assertion and attach it as the `x-autostock-webauthn` header on the permission-reply
// request. The server (U2) verifies it before approving any remote mutating tool.
//
// Browser APIs (fetch, navigator.credentials) are injected so the ceremony is unit-testable
// without a real authenticator. base64url helpers avoid a SimpleWebAuthn browser dep.

export type Fetcher = (path: string, init?: RequestInit) => Promise<Response>

export type CredentialsGet = (opts: {
  publicKey: PublicKeyCredentialRequestOptions
}) => Promise<Credential | null>

function bufToB64url(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf)
  let bin = ""
  for (const b of bytes) bin += String.fromCharCode(b)
  return btoa(bin).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "")
}

export function b64urlToBuf(s: string): ArrayBuffer {
  const pad = s.length % 4 === 0 ? "" : "=".repeat(4 - (s.length % 4))
  const bin = atob(s.replaceAll("-", "+").replaceAll("_", "/") + pad)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out.buffer
}

/** Convert server assert-options (base64url challenge/ids) into a credentials.get() request. */
export function optionsToRequest(options: {
  challenge: string
  rpId?: string
  timeout?: number
  userVerification?: UserVerificationRequirement
  allowCredentials?: Array<{ id: string; transports?: string[] }>
}): PublicKeyCredentialRequestOptions {
  return {
    challenge: b64urlToBuf(options.challenge),
    rpId: options.rpId,
    timeout: options.timeout,
    userVerification: options.userVerification ?? "required",
    allowCredentials: options.allowCredentials?.map((c) => ({
      type: "public-key" as const,
      id: b64urlToBuf(c.id),
      transports: c.transports as AuthenticatorTransport[] | undefined,
    })),
  }
}

/** Serialize an assertion into the JSON the server's verifyAuthenticationResponse expects. */
export function serializeAssertion(cred: PublicKeyCredential): string {
  const resp = cred.response as AuthenticatorAssertionResponse
  const json = {
    id: cred.id,
    rawId: bufToB64url(cred.rawId),
    type: cred.type,
    response: {
      authenticatorData: bufToB64url(resp.authenticatorData),
      clientDataJSON: bufToB64url(resp.clientDataJSON),
      signature: bufToB64url(resp.signature),
      userHandle: resp.userHandle ? bufToB64url(resp.userHandle) : undefined,
    },
    clientExtensionResults: {},
  }
  // The server reads the header as base64(JSON) (see webauthn.ts verifyAssertionHeader).
  return btoa(JSON.stringify(json))
}

export class WebAuthnError extends Error {}

/** Run the full ceremony; returns the header value to send on the permission reply. */
export async function obtainAssertionHeader(deps: {
  fetcher: Fetcher
  credentialsGet: CredentialsGet
}): Promise<string> {
  const res = await deps.fetcher("/autostock/webauthn/assert-options", { method: "POST" })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new WebAuthnError((body as { error?: string }).error ?? `assert-options ${res.status}`)
  }
  const options = await res.json()
  const cred = await deps.credentialsGet({ publicKey: optionsToRequest(options) })
  if (!cred) throw new WebAuthnError("사용자가 패스키 서명을 취소했습니다")
  return serializeAssertion(cred as PublicKeyCredential)
}

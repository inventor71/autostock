// F79 — bind the WebAuthn ceremony (webauthn-client/signed-mutation) to a real server:
// an authenticated Fetcher to the `/autostock/webauthn/*` endpoints (basic-auth, same creds
// as the SDK client) and the browser passkey API. Pure URL/header helpers are unit-tested;
// the browser/credential bits are injected so callers stay testable.

import type { ServerConnection } from "@/context/server"
import { authTokenFromCredentials } from "@/utils/server"
import type { CredentialsGet, Fetcher } from "./webauthn-client"

/** Authorization header value for the server's basic-auth. */
export function basicAuthHeader(http: { username?: string; password?: string }): string {
  return "Basic " + authTokenFromCredentials({ username: http.username, password: http.password ?? "" })
}

/** Join server base URL + path without doubling or dropping the slash. */
export function joinUrl(base: string, path: string): string {
  return base.replace(/\/+$/, "") + (path.startsWith("/") ? path : "/" + path)
}

/** Authenticated Fetcher to the autostock WebAuthn endpoints on this server. */
export function serverFetcher(http: ServerConnection.HttpBase, baseFetch: typeof fetch = fetch): Fetcher {
  const auth = basicAuthHeader(http)
  return (path, init) =>
    baseFetch(joinUrl(http.url, path), {
      ...init,
      headers: { ...(init?.headers as Record<string, string> | undefined), authorization: auth },
    })
}

/** Browser passkey assertion via the WebAuthn API. */
export function browserCredentialsGet(): CredentialsGet {
  return (opts) => navigator.credentials.get(opts as CredentialRequestOptions)
}

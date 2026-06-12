// F71 U3 — QR pairing: parse the `autostock qr` payload into a ServerConnection (US-1).
// Pure: no DOM/camera here (the scanner just hands us the decoded text). Inverse of the
// launcher's buildPairingPayload.
import { ServerConnection } from "@/context/server"

export type PairResult =
  | { ok: true; server: ServerConnection.Http }
  | { ok: false; reason: string }

/** Parse a scanned QR string into an http ServerConnection (url + password). */
export function parsePairingPayload(text: string): PairResult {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return { ok: false, reason: "QR 내용이 JSON이 아닙니다" }
  }
  if (typeof parsed !== "object" || parsed === null) {
    return { ok: false, reason: "QR 형식이 올바르지 않습니다" }
  }
  const p = parsed as Record<string, unknown>
  if (p.kind !== "autostock-pair") {
    return { ok: false, reason: "autostock 페어링 QR이 아닙니다" }
  }
  if (p.v !== 1) {
    return { ok: false, reason: `지원하지 않는 페어링 버전: ${String(p.v)}` }
  }
  const url = typeof p.url === "string" ? p.url.trim() : ""
  const password = typeof p.password === "string" ? p.password : ""
  if (!/^https?:\/\/.+/.test(url)) {
    return { ok: false, reason: "QR에 유효한 서버 URL이 없습니다" }
  }
  if (!password) {
    return { ok: false, reason: "QR에 서버 비밀번호가 없습니다" }
  }
  return {
    ok: true,
    server: { type: "http", http: { url, password, username: "opencode" } },
  }
}

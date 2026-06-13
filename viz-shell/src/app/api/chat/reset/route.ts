import { sessionFilePath } from "@/server/paths";
import { SessionStore } from "@/server/chat/session-store";
import { isTurnInFlight } from "@/server/chat/turn-lock";

/**
 * "New chat" (BR-14): drop the persisted session id. View files and tab state
 * are untouched — views persist independently of chat sessions (FR-6).
 */
export async function POST() {
  // Resetting mid-turn would race the turn's session.set on init (the deleted
  // session id gets re-persisted) — refuse like a concurrent chat POST (BR-15).
  if (isTurnInFlight()) {
    return Response.json(
      { error: "a chat turn is in progress — reset after it finishes" },
      { status: 409 },
    );
  }
  new SessionStore(sessionFilePath()).reset();
  console.log("[viz-shell:chat] session reset");
  return Response.json({ ok: true });
}

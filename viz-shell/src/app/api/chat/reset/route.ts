import { sessionFilePath } from "@/server/paths";
import { SessionStore } from "@/server/chat/session-store";

/**
 * "New chat" (BR-14): drop the persisted session id. View files and tab state
 * are untouched — views persist independently of chat sessions (FR-6).
 */
export async function POST() {
  new SessionStore(sessionFilePath()).reset();
  console.log("[viz-shell:chat] session reset");
  return Response.json({ ok: true });
}

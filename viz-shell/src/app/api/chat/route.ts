import { createUIMessageStream, createUIMessageStreamResponse } from "ai";

import { sessionFilePath } from "@/server/paths";
import { runTurn } from "@/server/chat/claude-runner";
import { SessionStore } from "@/server/chat/session-store";
import { releaseTurn, tryAcquireTurn } from "@/server/chat/turn-lock";
import type { VizUIMessage } from "@/lib/chat-types";

/** Pull the latest user message text out of the useChat payload. */
function extractPrompt(body: unknown): string {
  const messages = (body as { messages?: VizUIMessage[] })?.messages;
  if (!Array.isArray(messages)) return "";
  const lastUser = [...messages].reverse().find((m) => m?.role === "user");
  if (!lastUser || !Array.isArray(lastUser.parts)) return "";
  return lastUser.parts
    .filter((p): p is { type: "text"; text: string } => p?.type === "text")
    .map((p) => p.text)
    .join("\n")
    .trim();
}

export async function POST(req: Request) {
  let prompt: string;
  try {
    prompt = extractPrompt(await req.json());
  } catch {
    return Response.json({ error: "invalid request body" }, { status: 400 });
  }
  if (prompt === "") {
    return Response.json({ error: "empty prompt" }, { status: 400 });
  }
  // BR-15: single operator, single in-flight turn — no queueing.
  if (!tryAcquireTurn()) {
    return Response.json(
      { error: "a chat turn is already in progress" },
      { status: 409 },
    );
  }

  const session = new SessionStore(sessionFilePath());

  const stream = createUIMessageStream<VizUIMessage>({
    execute: async ({ writer }) => {
      let textId: string | null = null;
      let textCount = 0;
      const closeText = () => {
        if (textId !== null) {
          writer.write({ type: "text-end", id: textId });
          textId = null;
        }
      };
      try {
        await runTurn(prompt, session, (ev) => {
          switch (ev.type) {
            case "text-delta":
              if (textId === null) {
                textId = `txt-${++textCount}`;
                writer.write({ type: "text-start", id: textId });
              }
              writer.write({ type: "text-delta", id: textId, delta: ev.delta });
              break;
            case "tool-activity":
              closeText();
              writer.write({
                type: "data-tool-activity",
                data: { tool: ev.tool, target: ev.target },
              });
              break;
            case "boundary-denied":
              closeText();
              writer.write({
                type: "data-boundary-denied",
                data: { tool: ev.tool, target: ev.target, reason: ev.reason },
              });
              break;
          }
        });
      } finally {
        closeText();
        releaseTurn();
      }
    },
    onError: (error) => {
      releaseTurn(); // idempotent — covers stream-level failures too
      return error instanceof Error ? error.message : String(error);
    },
  });

  return createUIMessageStreamResponse({ stream });
}

import path from "node:path";

import { query } from "@anthropic-ai/claude-agent-sdk";

import { generatedDir, vizShellDir } from "@/server/paths";
import { createBoundary } from "@/server/chat/boundary";
import { sanitizeEnv } from "@/server/chat/sanitize-env";
import { VIEW_GENERATOR_CONTRACT } from "@/server/chat/view-contract";
import type { SessionStore } from "@/server/chat/session-store";

/** Stream events surfaced to the chat UI (E6 / BR-16). */
export type StreamEvent =
  | { type: "text-delta"; delta: string }
  | { type: "tool-activity"; tool: string; target: string }
  | { type: "boundary-denied"; tool: string; target: string; reason: string };

function summarizeTarget(input: unknown): string {
  if (typeof input !== "object" || input === null) return "";
  const rec = input as Record<string, unknown>;
  for (const key of ["file_path", "notebook_path", "path", "pattern"]) {
    const v = rec[key];
    if (typeof v === "string" && v.length > 0) {
      return path.isAbsolute(v) ? path.relative(vizShellDir(), v) : v;
    }
  }
  return "";
}

/**
 * One chat turn against the persistent single session (L3). Emits UI events;
 * resolves when the SDK stream ends. Never throws for agent-level errors —
 * they surface as an error event in the UI layer.
 */
export async function runTurn(
  prompt: string,
  session: SessionStore,
  emit: (ev: StreamEvent) => void,
  abortSignal?: AbortSignal,
): Promise<void> {
  const startedAt = Date.now();
  const resumeId = session.id;

  // Client disconnect/stop aborts the SDK turn instead of letting it run on.
  const abortController = new AbortController();
  if (abortSignal !== undefined) {
    if (abortSignal.aborted) abortController.abort();
    else abortSignal.addEventListener("abort", () => abortController.abort(), { once: true });
  }

  const boundary = createBoundary({
    vizShellDir: vizShellDir(),
    generatedDir: generatedDir(),
    onDeny: (ev) => emit({ type: "boundary-denied", ...ev }),
  });

  // BR-17: operational log only — no prompt body, no account values.
  console.log(
    `[viz-shell:chat] turn start session=${resumeId ?? "(new)"} promptChars=${prompt.length}`,
  );

  const stream = query({
    prompt,
    options: {
      cwd: vizShellDir(),
      permissionMode: "default",
      canUseTool: async (toolName, input) => boundary(toolName, input),
      resume: resumeId ?? undefined,
      env: sanitizeEnv(process.env),
      systemPrompt: {
        type: "preset",
        preset: "claude_code",
        append: VIEW_GENERATOR_CONTRACT,
      },
      // Defense-in-depth next to canUseTool (which stays authoritative and
      // deny-by-default for anything not listed here).
      disallowedTools: ["Bash", "WebFetch", "WebSearch", "Task", "TodoWrite"],
      includePartialMessages: true,
      abortController,
    },
  });

  for await (const msg of stream) {
    if (msg.type === "system" && msg.subtype === "init") {
      if (session.id === null) session.set(msg.session_id);
    } else if (msg.type === "stream_event") {
      const ev = msg.event;
      if (ev.type === "content_block_delta" && ev.delta.type === "text_delta") {
        emit({ type: "text-delta", delta: ev.delta.text });
      }
    } else if (msg.type === "assistant") {
      for (const block of msg.message.content) {
        if (block.type === "tool_use") {
          emit({
            type: "tool-activity",
            tool: block.name,
            target: summarizeTarget(block.input),
          });
        }
      }
    }
  }

  console.log(
    `[viz-shell:chat] turn end session=${session.id ?? "(unset)"} ms=${Date.now() - startedAt}`,
  );
}

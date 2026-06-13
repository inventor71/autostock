import type { UIMessage } from "ai";

/**
 * Chat message type shared by the /api/chat route and the ChatPanel.
 * Two custom data parts (BR-16): a one-line tool summary and a boundary denial.
 */
export type VizDataParts = {
  "tool-activity": { tool: string; target: string };
  "boundary-denied": { tool: string; target: string; reason: string };
};

export type VizUIMessage = UIMessage<unknown, VizDataParts>;

#!/usr/bin/env bun
// F4 Unit B — autostock steering MCP server (stdio). opencode connects to it and
// AUTO-GATES each tool via its permission system (session/tools.ts:135 calls
// ctx.ask({permission: "<server>:<tool>"}) before every MCP tool) — so the human
// confirm is enforced by opencode CORE, not by our code (this is why MCP is more
// robust than the plugin self-ask we kept breaking). Configure in opencode.json:
//   "mcp": { "autostock": { "type": "local",
//            "command": ["bun","run","<abs>/operator-console/src/mcp-server.ts"],
//            "environment": { "STEERING_DIR": "...", "STEERING_OPERATOR_TOKEN": "..." } } },
//   "permission": { "autostock_steer": "ask", "autostock_steer_read": "allow" }
// The deterministic parse + token + file-drop write live in src/steer-handler (tested);
// the daemon RiskManager gate is the final safety regardless.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { FileDrop } from "./filedrop";
import { handleSteer, handleSteerRead } from "./steer-handler";

const fd = new FileDrop(process.env.STEERING_DIR ?? "./steering");
const server = new McpServer({ name: "autostock", version: "0.0.0" });

server.registerTool(
  "steer",
  {
    description:
      "Steer the autostock trading daemon (MUTATING: buy/sell/flatten/flatten all/stop/" +
      "pause/resume/halt-entries/allow-entries/kill/approve/reject/unlock/note/directive). " +
      "Pass the operator command VERBATIM, e.g. '/sell AAPL 50%'. opencode asks the human to " +
      "confirm before this runs — you only propose; you cannot place an order yourself.",
    inputSchema: { command: z.string().describe("operator command, verbatim, e.g. /sell AAPL 50%") },
  },
  async ({ command }) => ({ content: [{ type: "text", text: handleSteer(command, fd) }] }),
);

server.registerTool(
  "steer_read",
  {
    description:
      "Read the autostock daemon state (status / positions / orders / agent-trace) — read-only, " +
      "no order authority. e.g. '/status', '/positions'.",
    inputSchema: { command: z.string().describe("a read command, e.g. /status") },
  },
  async ({ command }) => ({ content: [{ type: "text", text: handleSteerRead(command, fd) }] }),
);

await server.connect(new StdioServerTransport());

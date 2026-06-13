import { describe, expect, it } from "vitest";

import { sanitizeEnv } from "@/server/chat/sanitize-env";

describe("sanitizeEnv (BR-4)", () => {
  // Key names mirror the real autostock .env (names verified 2026-06-13).
  const dirty: NodeJS.ProcessEnv = {
    NODE_ENV: "test",
    PATH: "/usr/bin",
    HOME: "/home/op",
    STEERING_OPERATOR_TOKEN: "steer-secret",
    ALPACA_API_KEY: "ak",
    ALPACA_API_SECRET: "as",
    BROKER_API_KEY: "bk",
    BROKER_API_SECRET: "bs",
    FINNHUB_API_KEY: "fk",
    KIS_PAPER_ACCOUNT: "acct",
    KIS_PAPER_API_KEY: "kk",
    KIS_PAPER_API_SECRET: "ks",
    ANTHROPIC_API_KEY: "anth",
    OPENAI_API_KEY: "oai",
    CLAUDE_CODE_OAUTH_TOKEN: "oauth",
    SOME_FUTURE_TOKEN: "ft",
    SOME_DB_PASSWORD: "pw",
    KIS_SESSION_ID: "ksi", // non-conventional suffix — caught by family prefix
    ALPACA_BASE_URL: "abu",
    UNDEF: undefined,
  };

  const clean = sanitizeEnv(dirty);

  it.each([
    "STEERING_OPERATOR_TOKEN",
    "ALPACA_API_KEY",
    "ALPACA_API_SECRET",
    "BROKER_API_KEY",
    "BROKER_API_SECRET",
    "FINNHUB_API_KEY",
    "KIS_PAPER_ACCOUNT",
    "KIS_PAPER_API_KEY",
    "KIS_PAPER_API_SECRET",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "SOME_FUTURE_TOKEN",
    "SOME_DB_PASSWORD",
    "KIS_SESSION_ID",
    "ALPACA_BASE_URL",
  ])("strips %s", (key) => {
    expect(clean).not.toHaveProperty(key);
  });

  it("keeps benign keys", () => {
    expect(clean.PATH).toBe("/usr/bin");
    expect(clean.HOME).toBe("/home/op");
  });

  it("keeps CLAUDE_CODE_OAUTH_TOKEN (SDK child auth)", () => {
    expect(clean.CLAUDE_CODE_OAUTH_TOKEN).toBe("oauth");
  });

  it("drops undefined values", () => {
    expect(clean).not.toHaveProperty("UNDEF");
  });
});

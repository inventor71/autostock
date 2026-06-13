/**
 * Env hygiene for the SDK child process (BR-4). The chat agent must never see
 * trading/steering credentials — even though it cannot run Bash, this keeps
 * the secrets out of its process entirely (defense-in-depth).
 */

/** Kept despite matching the secret pattern: the SDK child needs it to auth. */
const KEEP = new Set(["CLAUDE_CODE_OAUTH_TOKEN"]);

/** Known sensitive keys present in the autostock .env (verified 2026-06-13). */
const DENY_EXACT = new Set([
  "STEERING_OPERATOR_TOKEN",
  "ANTHROPIC_API_KEY", // force subscription auth — no API billing from viz-shell
  "OPENAI_API_KEY",
  "KIS_PAPER_ACCOUNT",
]);

const DENY_SUFFIX =
  /(_API_KEY|_API_SECRET|_SECRET_KEY|_SECRET|_TOKEN|_PASSWORD|_CREDENTIALS)$/;

export function sanitizeEnv(env: NodeJS.ProcessEnv): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(env)) {
    if (value === undefined) continue;
    if (KEEP.has(key)) {
      out[key] = value;
      continue;
    }
    if (DENY_EXACT.has(key) || DENY_SUFFIX.test(key)) continue;
    out[key] = value;
  }
  return out;
}

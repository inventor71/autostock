# Stage 0 — Investigation (go/no-go): `claude -p` shared runner

**Track**: R5 · **Date**: 2026-06-06 · **Base**: 5e786b0

R5 was filed investigation-first: confirm the overlap is worth a helper before extracting.
**Conclusion: the overlap is ~12 lines and concentrated in the hot production agent brain →
recommend closing R5 as "won't-do".** Evidence below.

## The two wrappers
| | `ClaudeCodeClient.complete()` (`src/strategy/llm/client.py:198-244`) | `AgentSession._invoke()` (`src/agent/session.py:207-244`) |
|---|---|---|
| Purpose | single-shot text completion, tools disabled, throwaway cwd (backtest/dev) | resumable daily trading agent, tools enabled, workspace cwd, env scrubbing |
| argv | `-p --output-format json --model --system-prompt --disallowed-tools --no-session-persistence` | `-p --output-format json --model --permission-mode --allowedTools --resume/--session-id --append-system-prompt` |
| env | none (neutral) | scrub steering token + PYTHONPATH + venv PATH (F46) |
| retry | `_retry_with_backoff` (broad `except Exception`, no message inspection) | `run_turn` retries once on `_SESSION_ERROR_FRAGMENTS` **matched in the exception text** |
| returns | `payload["result"]` | full `payload` (→ `AgentTurnResult`) |

## The only genuinely shared code (~12 lines, post-`subprocess.run`)
Both do: returncode≠0 → raise; `json.loads(stdout)`; `is_error` → raise; use payload. Diffs:
- returncode message: **identical** text `"claude CLI exited with {rc}: {stderr}"` (agent None-safe on stderr).
- is_error message: `"claude CLI returned an error"` (strategy) vs `"claude returned an error"` (agent).
- JSON parse failure: agent wraps `JSONDecodeError`→`RuntimeError("Could not parse claude JSON output")`;
  strategy lets it raise raw (caught by its broad retry).
- return: `payload["result"]` vs full `payload`.

## Why "won't-do" (recommendation)
1. **Tiny dedup.** A `parse_claude_json(proc)->dict` helper removes ~6 lines per site (~12 total).
2. **Coupling risk on the high-stakes side.** The agent's retry-on-stale-session depends on the
   exception **text** (`_SESSION_ERROR_FRAGMENTS` in `session.py:273`). A shared helper must reproduce
   the agent's exact messages, so it can't actually simplify them — it just relocates them.
3. **The agent brain is hot + high-stakes.** `session.py` is the production trading orchestrator,
   actively touched by feature tracks (F69 live). Editing `_invoke` for ~6 lines invites merge
   conflicts and risk far out of proportion to the gain.
4. **Using the helper on only the strategy side achieves no dedup** (one caller = not shared).
5. **The orchestration is correctly different** (tools/sessions/env/retry) — the bulk is NOT
   duplicated; only the trivial envelope is, and even that carries the message-coupling caveat.

→ Net: the cure (touch two modules incl. the trading brain, reproduce exact messages) costs more
than the ~12-line disease. This matches the investigation-first expectation that R5 may close.

## Alternative if you still want it (minimal extraction)
Add `parse_claude_json(proc) -> dict` to `src/core/` and call it from both:
- **agent** stays byte-identical (helper reproduces its exact messages incl. stderr text → fragment
  matching intact).
- **strategy** gets 2 cosmetic changes: is_error message wording, and JSON-parse failures become
  `RuntimeError` instead of raw `JSONDecodeError` (both retried identically; final exception *type*
  changes on persistent failure). No test asserts these (grep: none) so nothing breaks.
This is a real but marginal T1/T2; the recommendation is still to skip it.

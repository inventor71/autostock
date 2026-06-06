# Pick-up guide — R5: `claude -p` headless runner

**Status**: backlog (not started). Survey base `ec2875c` (2026-06-06). **Investigation-first** —
this track may legitimately close as "won't do" if the overlap proves too thin.

## The two wrappers (and why they differ)
| | `ClaudeCodeClient.complete()` (`src/strategy/llm/client.py`) | `AgentSession` (`src/agent/session.py`) |
|---|---|---|
| Purpose | single-shot text completion for backtest/dev | daily resumable trading agent |
| Tools | **all disabled** (`--disallowed-tools …`) | **enabled** (Read/Write/Edit/Glob/Grep/Web + scoped Bash) |
| cwd | throwaway `TemporaryDirectory` (avoid project CLAUDE.md/hooks) | the **workspace** dir (journal lives there) |
| Session | `--no-session-persistence` | resumable `session_id`, collision-retry with fresh id |
| Output | `--output-format json` → `json.loads(stdout)["result"]` | same JSON envelope, richer `AgentTurnResult` |
| Retry | `_retry_with_backoff` (transient) | `_SESSION_ERROR_FRAGMENTS` → retry with new session id |
| Injectable runner | no | yes (`runner` param — used by tests) |

The **orchestration is correctly different**. Forcing them into one class would be a regression of
clarity, not an improvement. Do NOT do that.

## The actual shareable core (~30–40 lines)
Both, after `subprocess.run(...)`, do the same envelope dance:
1. check `returncode != 0` → raise with `stderr`
2. `payload = json.loads(stdout)`
3. check `payload.get("is_error")` / error result → raise
4. return `payload["result"]`

Candidate helper (in e.g. `src/core/claude_cli.py` or `src/agent/_claude_proc.py`):
```python
def parse_claude_json(proc: subprocess.CompletedProcess) -> dict:
    """returncode + JSON-envelope + is_error checks → parsed payload (raises on error)."""
```
Optionally also a `build_base_argv(cli_path, model, *, output_json=True)` for the common flags.
`AgentSession` already takes an injectable `runner`, so it should adopt the *parser* without
changing its `runner` seam.

## Investigation checklist (Stage 0 — do this before committing)
- [ ] Diff the exact post-`subprocess.run` blocks. Is it really the same 4 steps, or has each
      drifted (e.g. different keys checked)? If drifted, sharing risks re-introducing a bug.
- [ ] Does `AgentSession` ever read fields beyond `result` (it builds `raw=payload`)? The helper
      must return the full payload, not just `result`.
- [ ] Confirm the strategy path's `_retry_with_backoff` and the agent path's session-retry wrap the
      call at *different* layers — the shared helper must sit **inside** both retries, not replace them.
- [ ] Decision: extract `parse_claude_json` only (low risk, real dedup) vs also `build_base_argv`
      (more surface, the flag sets differ a lot — likely not worth it). Recommend: parser only.

## Tiering
- `parse_claude_json` extraction with both call sites preserved = **T1** if byte-identical logic.
- Any change to tool allowlist, permission mode, cwd, or session semantics = **T3** (security-
  relevant) — out of scope; flag and stop.

## Test net
`tests/test_agent.py` (drives `AgentSession` via injected `runner`), `tests/test_llm_formatter.py`,
`tests/test_multi_agent.py`. Add direct unit tests for `parse_claude_json`: ok payload,
non-zero returncode, `is_error=True`, malformed JSON.

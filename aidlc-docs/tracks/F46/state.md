# Track F46 — Agent `account` tool down: alpaca-py missing from the agent's `python3`

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F46
- **Title**: Agent `account` tool down — spawned agent's `python3` lacks alpaca-py (PATH gap)
- **Type**: feature (bug fix)
- **Status**: merged → main fb06517 (2026-06-03)
- **Branch**: feat/F46 (merged, deleted)
- **Worktree**: — (제거됨)
- **Submodule branch**: — (monorepo, post-F35; fix is in `src/`, not the console)
- **Base commit**: 777cf40
- **Start Date**: 2026-06-03

## Extension Configuration
- **Security Baseline**: Enabled. Applicable: SECURITY-15 (explicit/fail-closed error handling —
  AlpacaBroker already raises a clear `BrokerError("alpaca-py not installed")`; this fix removes the
  *cause*, not the guard). SECURITY-03 (no secrets in logs — fix touches PATH only, no creds). Others
  N/A (no web app/DB/IaC/auth surface changed).
- **Property-Based Testing**: N/A for this change (env-wiring fix, not a pure function). A targeted
  unit test on `_invoke`'s env construction covers it.

## Scope
The PM agent runs its read-only tools as Bash subprocesses, e.g.
`python -m src.agent.tools account`. The daemon spawns the `claude` CLI with an env whose `PATH`
(baked into the systemd `--user` unit as `Environment=PATH=<nvm-node-bin>:/usr/local/bin:/usr/bin:/bin`)
contains **no venv bin dir**. So inside the agent, `python3` resolves to `/usr/bin/python3`, which has
yfinance + pandas installed *system-wide* (data tools work) but **not alpaca-py** → the `account` tool's
`_broker()` → `AlpacaBroker` raises `BrokerError("alpaca-py not installed")`. The daemon process itself
is unaffected because its `ExecStart` uses an absolute venv interpreter.

**Fix** (single, root-cause, launch-context-agnostic): in `src/agent/session.py::_invoke`, prepend the
daemon's *own* interpreter bin dir (`os.path.dirname(sys.executable)`) to the agent subprocess `PATH`,
right beside the existing `PYTHONPATH = _REPO_ROOT` injection. Both injections make the spawned agent
use the daemon's Python environment: `PYTHONPATH` so `-m src.agent.tools` resolves the package;
`PATH` so `python`/`python3` resolve to the same interpreter (which has alpaca-py). This fixes every
launch context (systemd, docker-verify attach, foreground/tmux) without depending on the systemd unit
PATH. Related: [[daemon-claude-cli-path]] (same class of bare-PATH systemd gap, for `claude` itself).

## Stage Progress
- [x] Workspace Detection — reused (brownfield; RE artifacts exist)
- [x] Requirements Analysis — ✅ APPROVED 2026-06-03 (Minimal depth). Root cause confirmed.
- [x] User Stories — SKIP (internal agent-runtime fix, no user-facing change)
- [x] Workflow Planning — SKIP (trivial: single-file fix + test; folded into requirements)
- [x] Application Design — SKIP (no new components)
- [x] Units Generation — SKIP (single change)
- [x] Construction (per-unit Code Generation)
  - [x] U1 — PATH injection in session.py:_invoke (3 lines) + 2 unit tests. 640 tests green.
- [x] Build & Test — ✅ ALL GREEN (640 passed, 0 failures). Live account tool reaches AlpacaBroker (alpaca-py found).

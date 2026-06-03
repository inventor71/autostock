# F6 console-sidebar-upgrade · Build Instructions

> Branch `feat/console-sidebar-upgrade` (worktree `.claude/worktrees/console-sidebar-upgrade`).
> Two artifacts: the Python daemon (parent repo) + the opencode-fork console (submodule `operator-console/cli`).
> 0 new runtime deps.

## 1. Python daemon (no build step)
Pure Python; nothing to compile. Use the project venv.
```bash
cd .claude/worktrees/console-sidebar-upgrade
venv/bin/python -c "import src.agent.steering.runtime, src.core.trades, src.execution.brokers.alpaca_broker"  # import smoke
```

## 2. Console — deterministic core (parent `operator-console/src`, Bun)
No build; bun runs TS directly.
```bash
cd operator-console
~/.bun/bin/bun install          # if node_modules absent (already pinned deps)
```

## 3. Console — opencode fork UI (submodule `operator-console/cli`)
Heavier (Bun + OpenTUI + solid-js). Needs the submodule's deps installed (build-essential on first run).
```bash
cd operator-console/cli
bun install                      # first time may need: apt install build-essential
bun dev                          # launches the autostock console TUI from source
```
> ⚠ The submodule deps were NOT installed in the AI build environment — `tsgo` typecheck of the 3 changed
> TS files (`sidebar-width.ts`, `sidebar.tsx`, `autostock.tsx`) is a **user step** after `bun install`:
> ```bash
> cd operator-console/cli && bunx tsgo --noEmit   # expect 0 errors
> ```

## 4. Run the daemon (for live console checks)
```bash
cd .claude/worktrees/console-sidebar-upgrade
venv/bin/python main.py --mode agent --steering    # publishes steering/snapshot.json + monitor.json
```
Console env: `STEERING_DIR=<repo>/steering`, `STEERING_OPERATOR_TOKEN` shared with the daemon (see f4 wiring memo).

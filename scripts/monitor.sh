#!/usr/bin/env bash
#
# Launch (or re-attach) the autostock monitoring dashboard in tmux:
#
#   ┌─────────────────┬───────────────────────────┐
#   │ decisions.jsonl │ account dashboard (status) │
#   │   (live)        ├───────────────────────────┤
#   │                 │ agent log (autostock.log) │
#   └─────────────────┴───────────────────────────┘
#
# Usage:
#   scripts/monitor.sh         launch the dashboard (or attach if already running)
#   scripts/monitor.sh kill    stop the dashboard session
#
set -euo pipefail

SESSION="autostock"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/venv/bin/python"
[ -x "$PY" ] || PY="python"

if [ "${1:-}" = "kill" ]; then
  tmux kill-session -t "$SESSION" 2>/dev/null && echo "stopped '$SESSION'" || echo "no '$SESSION' session"
  exit 0
fi

# Already running -> just attach.
if tmux has-session -t "$SESSION" 2>/dev/null; then
  exec tmux attach -t "$SESSION"
fi

# pane 0 (left): live decision stream  (tail -F tolerates the file not existing yet)
tmux new-session -d -s "$SESSION" -c "$ROOT" \
  "tail -F workspace/decisions.jsonl 2>/dev/null | jq '.'"

# pane 1 (right-top): account dashboard
tmux split-window -h -t "$SESSION" -c "$ROOT" \
  "$PY scripts/status.py --loop"

# pane 2 (right-bottom): agent log
tmux split-window -v -t "$SESSION" -c "$ROOT" \
  "tail -F logs/autostock.log"

tmux select-pane -t "$SESSION":0.0
exec tmux attach -t "$SESSION"

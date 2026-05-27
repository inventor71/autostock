#!/usr/bin/env bash
#
# Open the autostock monitoring dashboard in tmux (3 panes):
#
#   ┌─────────────────┬───────────────────────────┐
#   │ decisions.jsonl │ account dashboard (status) │
#   │   (live)        ├───────────────────────────┤
#   ├─────────────────┤ agent log (autostock.log) │
#   │ turns + trades  │                            │
#   └─────────────────┴───────────────────────────┘
#
# Run inside tmux  -> opens the layout as a NEW WINDOW in the current session
# Run outside tmux -> creates a standalone session and attaches
# Already open     -> switches to the existing window / attaches the session
#
# Usage:
#   scripts/monitor.sh         open (or switch to) the dashboard
#   scripts/monitor.sh kill    close the dashboard window / session
#
set -euo pipefail

NAME="autostock"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/venv/bin/python"
[ -x "$PY" ] || PY="python"

DEC_CMD="tail -F workspace/decisions.jsonl 2>/dev/null | jq '.'"
STATUS_CMD="$PY scripts/status.py --loop 3"
# Re-colorize the plain log file at display time (loguru strips color in the
# file sink); see scripts/logcolor.awk.
LOG_CMD="tail -F logs/autostock.log | awk -f scripts/logcolor.awk"
# Turn telemetry (cost/activity per turn) + closed round-trips, as they happen,
# condensed to one scannable line each by scripts/events.jq.
EVENTS_CMD="tail -F workspace/turns.jsonl workspace/trades.jsonl 2>/dev/null | jq -Rr --unbuffered -f scripts/events.jq"

if [ "${1:-}" = "kill" ]; then
  if tmux kill-session -t "$NAME" 2>/dev/null; then echo "stopped session '$NAME'"; fi
  if [ -n "${TMUX:-}" ] && tmux kill-window -t "$NAME" 2>/dev/null; then echo "closed window '$NAME'"; fi
  exit 0
fi

# Build the 4-pane layout starting from a pane already running the decisions
# stream. $1 = that pane's id. Each pane gets a title shown on its top border.
build_layout() {
  local first="$1" right logp eventp
  right=$(tmux split-window -h -P -F '#{pane_id}'  -t "$first" -c "$ROOT" "$STATUS_CMD")
  logp=$(tmux split-window -v -P -F '#{pane_id}'   -t "$right" -c "$ROOT" "$LOG_CMD")
  eventp=$(tmux split-window -v -P -F '#{pane_id}' -t "$first" -c "$ROOT" "$EVENTS_CMD")

  tmux select-pane -t "$first"  -T "decisions (live)"
  tmux select-pane -t "$eventp" -T "turns + trades"
  tmux select-pane -t "$right"  -T "account dashboard"
  tmux select-pane -t "$logp"   -T "agent log"

  # Show each pane's title on its top border (active pane highlighted).
  tmux set-option -w -t "$first" pane-border-status top
  tmux set-option -w -t "$first" pane-border-format \
    "#{?pane_active,#[reverse],} #{pane_title} #[default]"

  tmux select-pane -t "$first"
}

if [ -n "${TMUX:-}" ]; then
  # Inside tmux: reuse the window if it already exists, else add a new one.
  if tmux list-windows -F '#{window_name}' | grep -qx "$NAME"; then
    exec tmux select-window -t "$NAME"
  fi
  first=$(tmux new-window -P -F '#{pane_id}' -n "$NAME" -c "$ROOT" "$DEC_CMD")
  build_layout "$first"
else
  # Outside tmux: attach the standalone session if running, else create it.
  if tmux has-session -t "$NAME" 2>/dev/null; then
    exec tmux attach -t "$NAME"
  fi
  first=$(tmux new-session -d -s "$NAME" -n "$NAME" -P -F '#{pane_id}' -c "$ROOT" "$DEC_CMD")
  build_layout "$first"
  exec tmux attach -t "$NAME"
fi

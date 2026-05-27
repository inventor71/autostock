# Compact one-liners for the monitor's "turns + trades" pane.
#
# Fed by:  tail -F workspace/turns.jsonl workspace/trades.jsonl | jq -Rr -f events.jq
#
# Input is raw lines (jq -R): tail's "==> file <==" headers and blank lines
# fail `fromjson?` and are dropped. Records self-identify — turn rows have
# .turn_type, trade rows have .symbol — so the file they came from is irrelevant.

def c(code): "\u001b[\(code)m";   # ANSI SGR
def reset:  c("0");
def hm:     .[11:16];             # "2026-05-27T23:45:42..." -> "23:45"

fromjson?
| if .turn_type then
    "\(.ts|hm)  \(c("36"))turn\(reset) \(.turn_type)  \(c("2"))\(.model)\(reset)  "
    + "\(.num_turns) steps  \(.num_decisions) dec  "
    + "$\((.cost_usd*1000|round)/1000)  \((.duration_ms/1000)|floor)s  "
    + "\(c("2"))io \(.input_tokens)/\(.output_tokens)\(reset)"
  elif .symbol then
    (if .realized_pnl >= 0 then c("32") else c("31") end) as $p
    | "\(.closed_at|hm)  \(c("33"))TRADE\(reset) \(.symbol)  "
    + "\(.qty) @ \(.entry_price)→\(.exit_price)  "
    + "\($p)\(.realized_pnl) (\(.return_pct)%)\(reset)"
  else empty end

#!/usr/bin/awk -f
#
# Re-colorize plain loguru log lines on the way to a terminal.
#
# The file sink in src/monitoring/logger.py strips color markup (loguru does
# this automatically for non-TTY sinks), so logs/autostock.log is plain text.
# This filter reconstructs loguru's default palette at display time, so the
# monitor pane looks like the live `python` run without polluting the log file.
#
# Used by scripts/monitor.sh:  tail -F logs/autostock.log | awk -f logcolor.awk
#
# Loguru line format (see LOG_FORMAT in logger.py):
#   {time} | {level: <8} | {name}:{function}:{line} - {message}
# Lines that don't match (e.g. exception tracebacks) pass through untouched.

BEGIN {
    e     = sprintf("%c", 27)        # ESC, portable across mawk/gawk
    green = e "[32m"
    cyan  = e "[36m"
    reset = e "[0m"
    bold  = e "[1m"

    # Loguru's default per-level colors.
    lcolor["TRACE"]    = e "[36m"            # cyan
    lcolor["DEBUG"]    = e "[34m"            # blue
    lcolor["INFO"]     = e "[1m"             # bold
    lcolor["SUCCESS"]  = e "[32m"            # green
    lcolor["WARNING"]  = e "[33m"            # yellow
    lcolor["ERROR"]    = e "[31m"            # red
    lcolor["CRITICAL"] = e "[1m" e "[41m"    # bold on red background
}

{
    line = $0

    # Split off the timestamp at the first " | " and sanity-check its shape.
    p1 = index(line, " | ")
    ts = substr(line, 1, p1 - 1)
    if (p1 == 0 || ts !~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]\.[0-9][0-9][0-9]$/) {
        print line
        fflush()
        next
    }

    # Level field (padded to 8), then the rest.
    rest = substr(line, p1 + 3)
    p2 = index(rest, " | ")
    if (p2 == 0) { print line; fflush(); next }
    level = substr(rest, 1, p2 - 1)
    rest2 = substr(rest, p2 + 3)

    # location ("name:function:line", no spaces) and message split at first " - ".
    p3 = index(rest2, " - ")
    if (p3 == 0) { loc = rest2; msg = "" }
    else         { loc = substr(rest2, 1, p3 - 1); msg = substr(rest2, p3 + 3) }

    lv = level
    gsub(/ /, "", lv)
    c = lcolor[lv]
    if (c == "") c = bold

    printf "%s%s%s | %s%s%s | %s%s%s - %s%s%s\n", \
        green, ts, reset, \
        c, level, reset, \
        cyan, loc, reset, \
        c, msg, reset
    fflush()
}

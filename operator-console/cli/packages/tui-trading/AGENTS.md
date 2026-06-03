This package renders the trading TUI (timeline bar, markers, sidebar, status).

## Keep the UI legend in sync (F28)

When you add, change, or remove a **visible TUI element** here — a timeline marker
glyph, the topbar `$cost`, date navigation, a sidebar block (account / positions /
round-trip / fills), or a status indicator (RUNNING / MKT) — also update the matching
entry in `operator-console/src/ui-legend.json` (parent repo).

That file is the static dictionary the normal-mode agent serves via
`steer_read {command:"/ui-legend"}` so it can explain on-screen elements to the user.
If the UI drifts from the legend, the agent's explanation goes stale. Update both in
the same change.

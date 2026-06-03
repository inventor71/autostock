# F6 console-sidebar-upgrade · Integration & Live Verification

End-to-end the seam is: **daemon publishes `steering/{snapshot,monitor}.json`** → **console reads** (sidebar poll +
`steer_read`). Cross-language contract is pinned by `operator-console/test/contract.test.ts` (TS schema ↔ Python pydantic) —
F6 added only additive read-view fields, so the contract is unchanged.

## Automated integration (covered by unit tests)
- Python: `publish_snapshot`/`publish_monitor` write real files on the worker; tests read them back.
- TS: `handleSteerRead` reads a written `monitor.json` and routes per verb.
No separate harness needed — the file-drop seam is exercised on both sides.

## Live verification (manual — needs the opencode TUI + a paper account)
Run the daemon (`main.py --mode agent --steering`) and the console (`bun dev`) against the **paper** account.

| ID | Check | How | Status |
|----|-------|-----|--------|
| **R1** | Drag-resize works; width persists across restart | `<leader>b` show sidebar → drag its left edge; resize takes; relaunch → width restored from `~/.local/state/autostock-console/ui.json` | ✅ **confirmed 2026-05-30** |
| **R3** | `steer_read` views | In console NL: ask for turn costs / recent decisions / agent log → tool returns the `monitor.json` slice (not the snapshot) | ⏳ later |
| **R4** | `get_fills` intraday round-trip | With paper fills today, sidebar shows `today  W..% (n)  +$..`; verify it populates **during** the session (not only post-EOD) | ⏳ later |

### R3/R4 quick checks (without the full TUI)
```bash
# R4: does the daemon compute today's round-trip from broker fills?
venv/bin/python -c "from src.execution.brokers.alpaca_broker import AlpacaBroker; \
from src.core.trades import summarize_today_round_trips; \
b=AlpacaBroker(...paper...); print(summarize_today_round_trips(b.get_fills(since='2026-01-01')))"
# R3: monitor.json shape after the daemon has run a few cycles
cat steering/monitor.json | jq '{turns: .turns.today_count, decisions: (.decisions|length), log: (.log|length)}'
```

## Safety / no-regression gates (must hold)
- Order / steering / privilege-separation path **unchanged** (F6 is read-only additions). Full Python suite **292 green**.
- New snapshot fields are **additive** → a console reading an old daemon (or vice versa) hides the blocks (BR-8), no crash.
- Secrets never in `monitor.json` log tail (`_mask_secrets`, SECURITY-03).

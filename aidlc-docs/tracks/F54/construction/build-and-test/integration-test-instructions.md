# F54 — Integration & Live Verification Instructions

## In-process integration (executor + broker + risk)
Covered by `tests/test_short_risk.py::TestAutoFlip` and `TestSqueezeGuardWired`:
auto-flip long↔short through the real DecisionExecutor → RiskManager → SimulatedBroker,
flat-check abort, and the squeeze guard firing via real `prev_close` plumbing.

```bash
/home/jihoonpark/Project/autostock/venv/bin/python -m pytest \
  tests/test_short_risk.py -k "Flip or Squeeze" -q
```

## Live verification (read-only, paper account) — per worktree-live-verification memory
```bash
VENV=/home/jihoonpark/Project/autostock/venv/bin/python
cd .claude/worktrees/F54   # .env linked by worktree-setup.sh; main venv has alpaca-py

$VENV -m src.agent.tools short_data TSLA   # real yfinance short interest + squeeze flag
$VENV -m src.agent.tools account           # real Alpaca paper: positions show side + dir-aware pct
```

Read-only only — do NOT place a live short order from verification. The short order
path (SELL_SHORT/BUY_TO_COVER → broker) is covered by SimulatedBroker integration
tests + Order structural validation.

**Result (2026-06-04): PASSED** — short_data returned real data (TSLA squeeze_risk=LOW);
account rendered 3 live long positions with the new side field, no error.

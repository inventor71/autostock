# F54 — Performance Test Instructions

**N/A** — single local daemon, no new hot paths or network calls.

- `Position.update_price`: one extra `if side == SHORT` branch — negligible.
- `RiskManager.evaluate_signal`: two added O(1) branches.
- `short_data`: one yfinance `Ticker.info` call, same cost as the existing
  `fundamentals` tool; agent-invoked on demand, not in any tight loop.
- `_prev_close`: one `get_bars(limit=2)` per SELL_SHORT decision (rare path).

No load/latency guards required beyond the existing F3/F14 daemon timeouts.

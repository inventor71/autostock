"""Market-signal collection for the research turn (F61).

Surfaces what just moved in the market and how it reads through to other names:
- mover scan (universe + bellwether watchlist),
- read-through propagation via a static peer map (final judgement left to the agent),
- imminent-earnings calendar.

The pure core (movers/peer_map/readthrough/earnings_cal/brief) is deterministic and
network-free; the impure boundary (collector + sources) is timeout-bounded and
fail-honest. The assembled ``MarketSignalBrief`` is both pushed into the research
prompt and exposed via on-demand tools.
"""

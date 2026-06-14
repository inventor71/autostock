"""Disclosed-holdings signal source (F81) — source-agnostic.

A *provider* fetches one manager's publicly disclosed holdings (e.g. an SEC
Form 13F-HR) and normalizes them into a :class:`HoldingsSnapshot`. Everything
downstream — the universe overlay, the research-brief section, the cache store,
the daemon refresher — depends ONLY on ``HoldingsSnapshot`` and never on any one
filing format. Adding another disclosure source (13D/G, a different regulator,
a manual list) is a new ``HoldingsProvider`` implementation registered in
``provider.py`` — overlay/brief/store/refresher do not change.

Mirrors the F77 retail-sentiment pattern: the daemon refresher does the only
HTTP (periodically) and writes a normalized snapshot to ``workspace/holdings/``;
the research turn and universe resolution READ that cache only (no HTTP, never
crashes the turn — fail-honest).
"""

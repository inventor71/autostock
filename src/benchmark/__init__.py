"""F70 — shadow benchmark: deterministic baselines as a measuring stick.

The live trading path runs the LLM agent alone. This package runs classic
deterministic strategies (buy & hold + technical) as **shadow paper portfolios**
on dedicated sandbox accounts, records their equity alongside the LLM account,
and computes alpha-vs-baseline. Baselines are a benchmark, not a competitor:
the question is whether the LLM actually beats a dumb floor enough to earn its
cost. See ``aidlc-docs/tracks/F70/``.
"""

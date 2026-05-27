"""Agent-facing market tools.

Small functions that the PM agent invokes via
``python -m src.agent.tools <cmd> ...`` to pull market data on demand (rather
than being fed one pre-formatted text blob). Logic lives in ``market.py`` with
injectable data sources so it is testable without network access; ``__main__``
wires the real providers and prints JSON.
"""

from src.agent.tools.market import (
    fundamentals,
    indicators,
    news,
    quote,
    scoreboard,
)

__all__ = ["quote", "indicators", "scoreboard", "fundamentals", "news"]

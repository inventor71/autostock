"""Intraday market-data pipeline: collection → per-session features → CSV store → analysis.

Role boundary (R10): this package owns intraday *data* — fetching minute bars
(``collector``), computing per-session features (``features``), persisting them
(``store``, CSV under the gitignored ``data/intraday/`` directory), and offline
hypothesis analysis (``analysis``). The agent's intraday *decision loop* (brief
assembly, wake events, watch triggers) lives in ``src/agent/intraday/`` and does
not depend on this package.

CLI entry points::

    python -m src.data.intraday.collector backfill --days 30
    python -m src.data.intraday.analysis [--symbols AAPL ...]
"""

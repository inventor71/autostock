"""Market timezone (US equities) — the single source of truth for ``ET``.

US equity sessions are anchored to the exchange timezone: a regular session crosses the local
(e.g. KST) midnight, so trading days are keyed by the *Eastern* calendar date, not the machine's.
``America/New_York`` is the canonical spelling (``US/Eastern`` is a tz-database alias with identical
offset + DST rules). ``core`` depends on nothing, so every layer can import this without creating an
upward dependency.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def et_now() -> datetime:
    """Current instant as a timezone-aware ET datetime."""
    return datetime.now(ET)


def et_today() -> date:
    """Current US/Eastern trading date (matches ``AgentSession.session_date``)."""
    return et_now().date()

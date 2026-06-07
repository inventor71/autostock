"""R6 — characterization + unit tests for the shared market-timezone helper.

The consolidation (one ``ET`` constant + ``et_now``/``et_today`` in ``src.core.markettime``)
normalizes two spellings of the US market timezone: ``US/Eastern`` (a tz-database backward-compat
alias) and ``America/New_York``. The alias-equivalence test is the behavior-preserving (T1) proof:
if the two spellings resolve identically across the DST boundary, normalizing to the canonical
``America/New_York`` changes nothing observable.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.core.markettime import ET, et_now, et_today


class TestAliasEquivalence:
    """``US/Eastern`` and ``America/New_York`` are the same zone (offset + DST)."""

    def test_winter_offset_identical(self):
        ny = datetime(2026, 1, 15, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        eastern = datetime(2026, 1, 15, 12, 0, tzinfo=ZoneInfo("US/Eastern"))
        assert ny.utcoffset() == eastern.utcoffset()  # EST -05:00

    def test_summer_offset_identical(self):
        ny = datetime(2026, 7, 15, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        eastern = datetime(2026, 7, 15, 12, 0, tzinfo=ZoneInfo("US/Eastern"))
        assert ny.utcoffset() == eastern.utcoffset()  # EDT -04:00

    def test_canonical_constant_matches_both_spellings(self):
        for d in (datetime(2026, 1, 15, 12), datetime(2026, 7, 15, 12)):
            assert d.replace(tzinfo=ET).utcoffset() == d.replace(
                tzinfo=ZoneInfo("US/Eastern")
            ).utcoffset()
            assert d.replace(tzinfo=ET).utcoffset() == d.replace(
                tzinfo=ZoneInfo("America/New_York")
            ).utcoffset()


class TestEtHelpers:
    def test_et_today_is_current_et_date(self):
        assert et_today() == datetime.now(ET).date()
        assert isinstance(et_today(), date)

    def test_et_now_is_tz_aware_et(self):
        now = et_now()
        assert now.tzinfo is ET
        # within a few seconds of a fresh ET read
        assert abs((now - datetime.now(ET)).total_seconds()) < 5

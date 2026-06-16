"""F89: 13F disclosed holdings are reference-only — NOT pushed into the every-turn
brief; reachable only via the on-demand `disclosed_holdings` pull tool (the data is
still collected so the tool works). Universe injection is controlled separately by
the per-provider `overlay` flag (off → reference-only).
"""

from __future__ import annotations

from datetime import date, datetime

from src.agent.tools import market
from src.signals.brief import to_prompt_text
from src.signals.records import MarketSignalBrief
from src.signals.holdings.records import HoldingsHighlight


def _mixed_highlight():
    return HoldingsHighlight(
        source_id="sec_13f:1", manager_name="SA LP", as_of=date(2026, 3, 31),
        long_top=["CLSK", "RIOT"], short_top=["NVDA", "AVGO"],
        new=["RIOT"], exited=["AAPL"], unmapped_n=2)


# --------------------------------------------------------------------------- #
# Push brief — 13F is NOT pushed at all (reference-only)
# --------------------------------------------------------------------------- #
def test_push_brief_omits_disclosed_holdings_entirely():
    text = to_prompt_text(MarketSignalBrief(disclosed_holdings=[_mixed_highlight()]))
    # Neither longs, shorts, nor any 13F header leak into the every-turn push brief.
    for token in ("CLSK", "RIOT", "NVDA", "AVGO", "13F", "기관"):
        assert token not in text, f"{token!r} should not be in the push brief"


def test_push_brief_holdings_only_yields_no_section():
    # A brief whose ONLY content is disclosed holdings has nothing to push.
    assert "13F" not in to_prompt_text(MarketSignalBrief(disclosed_holdings=[_mixed_highlight()]))


# --------------------------------------------------------------------------- #
# Pull tool — the full picture (incl. SHORT) is still available on demand
# --------------------------------------------------------------------------- #
class _FakeCollector:
    def collect(self, **_):
        return MarketSignalBrief(as_of=datetime(2026, 4, 1), disclosed_holdings=[_mixed_highlight()])


def test_pull_tool_still_returns_full_incl_short():
    out = market.disclosed_holdings(_FakeCollector())
    assert out["disclosed_holdings"][0]["short_top"] == ["NVDA", "AVGO"]
    assert out["disclosed_holdings"][0]["long_top"] == ["CLSK", "RIOT"]
    assert "as_of" in out and "degraded_sources" in out

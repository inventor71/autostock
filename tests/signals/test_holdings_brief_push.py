"""F87: 13F brief bias mitigation — the every-turn PUSH brief shows only the LONG
side; the bearish/put SHORT side is reachable only via the on-demand pull tool.
"""

from __future__ import annotations

from datetime import date, datetime

from src.agent.tools import market
from src.signals.brief import to_prompt_text
from src.signals.holdings.brief import render_push_line
from src.signals.holdings.records import HoldingsHighlight
from src.signals.records import MarketSignalBrief


def _mixed_highlight():
    return HoldingsHighlight(
        source_id="sec_13f:1", manager_name="SA LP", as_of=date(2026, 3, 31),
        long_top=["CLSK", "RIOT"], short_top=["NVDA", "AVGO"],
        new=["RIOT"], exited=["AAPL"], unmapped_n=2)


# --------------------------------------------------------------------------- #
# render_push_line — long-only
# --------------------------------------------------------------------------- #
def test_push_line_shows_longs_not_shorts():
    line = render_push_line(_mixed_highlight())
    assert "LONG CLSK,RIOT" in line
    assert "SHORT" not in line and "NVDA" not in line and "AVGO" not in line
    assert "unmapped 2" in line


def test_push_line_empty_when_no_longs():
    h = HoldingsHighlight(source_id="s", manager_name="X", as_of=date(2026, 3, 31),
                          long_top=[], short_top=["NVDA"])
    assert render_push_line(h) == ""  # all-short manager → no push line (no bearish hint)


# --------------------------------------------------------------------------- #
# to_prompt_text — the push brief never leaks the short side
# --------------------------------------------------------------------------- #
def test_prompt_text_omits_short_side():
    brief = MarketSignalBrief(disclosed_holdings=[_mixed_highlight()])
    text = to_prompt_text(brief)
    assert "CLSK" in text                      # long shown
    assert "NVDA" not in text and "SHORT" not in text  # short omitted from push
    assert "disclosed_holdings" in text        # points the agent at the pull tool


def test_prompt_text_no_section_when_only_shorts():
    h = HoldingsHighlight(source_id="s", manager_name="X", as_of=date(2026, 3, 31),
                          long_top=[], short_top=["NVDA"])
    text = to_prompt_text(MarketSignalBrief(disclosed_holdings=[h]))
    assert "13F long positions" not in text    # nothing to push → no section header


# --------------------------------------------------------------------------- #
# pull tool — the full picture (incl. SHORT) is available on demand
# --------------------------------------------------------------------------- #
class _FakeCollector:
    def collect(self, **_):
        return MarketSignalBrief(as_of=datetime(2026, 4, 1), disclosed_holdings=[_mixed_highlight()])


def test_pull_tool_includes_short_side():
    out = market.disclosed_holdings(_FakeCollector())
    assert out["disclosed_holdings"][0]["short_top"] == ["NVDA", "AVGO"]
    assert out["disclosed_holdings"][0]["long_top"] == ["CLSK", "RIOT"]
    assert "as_of" in out and "degraded_sources" in out

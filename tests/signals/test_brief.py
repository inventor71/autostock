"""Unit tests for brief assembly + rendering (F61, FR-5)."""

from datetime import date

from src.signals.brief import assemble_brief, to_prompt_text
from src.signals.records import ImminentEarnings, Mover, ReadThroughAlert


def _mover(sym, chg, in_uni=True):
    return Mover(symbol=sym, change_pct=chg, volume_ratio=3.0, close=10.0,
                 direction="up" if chg >= 0 else "down", in_universe=in_uni,
                 qualified_by=["price"])


def test_empty_brief_renders_blank():
    brief = assemble_brief([], [], [])
    assert brief.is_empty()
    assert to_prompt_text(brief) == ""


def test_rendered_text_contains_sections():
    movers = [_mover("AVGO", -15.0)]
    alerts = [ReadThroughAlert(trigger_symbol="AVGO", trigger_change_pct=-15.0,
                               cause_hint="guidance miss", affected_peers=["NVDA", "AMD"],
                               groups=["semis"])]
    earnings = [ImminentEarnings(symbol="NVDA", earnings_date=date(2026, 6, 6),
                                 when="amc", is_held=True, peer_readthrough=["AMD"])]
    text = to_prompt_text(assemble_brief(movers, alerts, earnings))
    assert "AVGO" in text and "-15.0%" in text
    assert "NVDA, AMD" in text
    assert "guidance miss" in text
    assert "[HELD]" in text
    assert "2026-06-06" in text


def test_watch_only_tag_for_out_of_universe():
    text = to_prompt_text(assemble_brief([_mover("XLE", 9.0, in_uni=False)], [], []))
    assert "watch-only" in text


def test_degraded_sources_rendered_even_if_empty_signals():
    brief = assemble_brief([], [], [], degraded_sources=["earnings:finnhub"])
    assert brief.is_empty()  # is_empty ignores degraded (no signal content)
    text = to_prompt_text(brief)  # but degraded still surfaces (fail-honest)
    assert text != ""
    assert "earnings:finnhub" in text

"""Unit tests for brief assembly + rendering (F61, FR-5)."""

from datetime import date

from src.signals.brief import assemble_brief, to_prompt_text
from src.signals.records import ImminentEarnings, ImminentIpo, Mover, ReadThroughAlert


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


def test_imminent_ipos_rendered():  # F78
    ipos = [
        ImminentIpo(name="SpaceX", symbol="SPCX", ipo_date=date(2026, 6, 12),
                    exchange="NASDAQ", status="priced", est_value=75.1e9),
        ImminentIpo(name="Acme", ipo_date=date(2026, 6, 16), status="expected",
                    est_value=1.2e9, in_universe=True),
    ]
    brief = assemble_brief([], [], [], imminent_ipos=ipos)
    assert not brief.is_empty()  # IPOs alone are signal content
    text = to_prompt_text(brief)
    assert "Imminent IPOs / catalysts" in text
    assert "NOT a buy menu" in text
    assert "SPCX (SpaceX) 2026-06-12 NASDAQ ~$75.1B [priced]" in text
    assert "(Acme) 2026-06-16 ~$1.2B [expected] [universe]" in text


def test_sentiment_outliers_rendered(  # F77
):
    from src.signals.records import SentimentOutlier

    outlier = SentimentOutlier(
        symbol="NVDA", bull_ratio=0.45, baseline_ratio=0.78,
        ratio_z=-2.7, tagged_n=22, direction="bearish")
    brief = assemble_brief([], [], [], sentiment_outliers=[outlier])
    assert not brief.is_empty()  # sentiment alone is signal content
    text = to_prompt_text(brief)
    assert "Retail sentiment" in text
    assert "NVDA bull 45%" in text and "usually 78%" in text
    assert "z=-2.7" in text
    assert "bearish shift" in text

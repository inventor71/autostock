"""SEC 13F provider (F81): filing selection, parsing, direction, hardening, build.

The provider is the only EDGAR-aware module; these tests pin the fragile bits with
NO network — a realistic information-table XML fixture and a fake submissions dict.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.signals.holdings.providers.sec_13f import (
    Sec13FProvider,
    _safe_parse_xml,
    build_sec_13f_provider,
)

_NS = "http://www.sec.gov/edgar/document/thirteenf/informationtable"


def _info(issuer, cusip, value, shares, put_call=None):
    pc = f"<ns:putCall>{put_call}</ns:putCall>" if put_call else ""
    return f"""
  <ns:infoTable>
    <ns:nameOfIssuer>{issuer}</ns:nameOfIssuer>
    <ns:titleOfClass>COM</ns:titleOfClass>
    <ns:cusip>{cusip}</ns:cusip>
    <ns:value>{value}</ns:value>
    <ns:shrsOrPrnAmt>
      <ns:sshPrnamt>{shares}</ns:sshPrnamt>
      <ns:sshPrnamtType>SH</ns:sshPrnamtType>
    </ns:shrsOrPrnAmt>
    {pc}
    <ns:investmentDiscretion>SOLE</ns:investmentDiscretion>
    <ns:votingAuthority><ns:Sole>{shares}</ns:Sole></ns:votingAuthority>
  </ns:infoTable>"""


def _table(*rows: str) -> str:
    body = "".join(rows)
    return f'<?xml version="1.0"?><ns:informationTable xmlns:ns="{_NS}">{body}</ns:informationTable>'


def _provider() -> Sec13FProvider:
    # request_gap_s=0 so tests never sleep.
    return Sec13FProvider(cik="0002045724", manager_name="SA LP", request_gap_s=0.0)


# --------------------------------------------------------------------------- #
# Parsing + direction normalization
# --------------------------------------------------------------------------- #
def test_parse_normalizes_put_to_short_and_share_to_long():
    xml = _table(
        _info("NVIDIA", "67066G104", 8_000_000, 1000, put_call="Put"),   # PUT → SHORT
        _info("CLEANSPARK", "18452B209", 2_000_000, 5000),               # share → LONG
    )
    rows, unmapped = _provider()._parse_info_table(xml)
    by = {(r.ticker, r.side): r for r in rows}
    assert by[("NVDA", "SHORT")].put_call == "PUT"
    assert by[("CLSK", "LONG")].put_call is None
    assert unmapped == 0


def test_call_is_long():
    xml = _table(_info("CLEANSPARK", "18452B209", 1000, 10, put_call="Call"))
    rows, _ = _provider()._parse_info_table(xml)
    assert rows[0].side == "LONG" and rows[0].put_call == "CALL"


def test_unmapped_cusip_is_dropped_and_counted():
    xml = _table(
        _info("KNOWN", "67066G104", 1000, 1, None),         # NVDA
        _info("MYSTERY CORP", "999999999", 1000, 1, None),  # not in map → unmapped
    )
    rows, unmapped = _provider()._parse_info_table(xml)
    assert [r.ticker for r in rows] == ["NVDA"]
    assert unmapped == 1


def test_weight_normalized_over_total_including_unmapped():
    xml = _table(
        _info("NVIDIA", "67066G104", 750, 1, None),     # mapped, 75% of total
        _info("MYSTERY", "999999999", 250, 1, None),    # unmapped but counts to total
    )
    rows, _ = _provider()._parse_info_table(xml)
    assert rows[0].ticker == "NVDA"
    assert abs(rows[0].weight - 0.75) < 1e-9


def test_same_issuer_same_side_aggregates():
    xml = _table(
        _info("NVIDIA", "67066G104", 600, 10, None),
        _info("NVIDIA", "67066G104", 400, 20, None),
    )
    rows, _ = _provider()._parse_info_table(xml)
    nvda = [r for r in rows if r.ticker == "NVDA"]
    assert len(nvda) == 1
    assert nvda[0].value_usd == 1000 and nvda[0].shares == 30


def test_long_and_short_of_same_name_stay_separate():
    xml = _table(
        _info("NVIDIA", "67066G104", 100, 1, None),         # LONG
        _info("NVIDIA", "67066G104", 100, 1, put_call="Put"),  # SHORT
    )
    rows, _ = _provider()._parse_info_table(xml)
    sides = sorted(r.side for r in rows if r.ticker == "NVDA")
    assert sides == ["LONG", "SHORT"]


# --------------------------------------------------------------------------- #
# Filing selection (FR-8)
# --------------------------------------------------------------------------- #
def _subs(*triples):
    forms = [t[0] for t in triples]
    accns = [t[1] for t in triples]
    dates = [t[2] for t in triples]
    return {"filings": {"recent": {"form": forms, "accessionNumber": accns, "filingDate": dates}}}


def test_latest_13f_picks_newest_and_includes_amendment():
    subs = _subs(
        ("13F-HR", "0000000000-25-000001", "2025-02-14"),
        ("13F-HR/A", "0000000000-25-000009", "2025-05-20"),  # newest, amendment
        ("13F-HR", "0000000000-24-000005", "2024-11-14"),
    )
    accn, d = _provider()._latest_13f(subs)
    assert accn == "0000000000-25-000009" and d == date(2025, 5, 20)


def test_latest_13f_skips_13f_nt_notice():
    subs = _subs(
        ("13F-NT", "0000000000-25-000010", "2025-06-01"),   # notice, no info table
        ("13F-HR", "0000000000-25-000001", "2025-02-14"),
    )
    accn, _ = _provider()._latest_13f(subs)
    assert accn == "0000000000-25-000001"


def test_latest_13f_raises_when_none():
    with pytest.raises(ValueError):
        _provider()._latest_13f(_subs(("10-K", "0000000000-25-000001", "2025-02-14")))


# --------------------------------------------------------------------------- #
# XML hardening (SECURITY-13)
# --------------------------------------------------------------------------- #
def test_doctype_is_rejected():
    evil = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "boom">]><x>&a;</x>'
    with pytest.raises(ValueError):
        _safe_parse_xml(evil)


def test_clean_xml_parses():
    assert _safe_parse_xml("<x><y>1</y></x>").tag == "x"


# --------------------------------------------------------------------------- #
# Builder validation (SECURITY-05)
# --------------------------------------------------------------------------- #
class _Settings:
    signals = {"disclosed_holdings": {"user_agent": "t/1.0 (c)", "request_gap_s": 0}}


def test_build_rejects_bad_cik():
    assert build_sec_13f_provider({"type": "sec_13f", "cik": "abc"}, _Settings()) is None
    assert build_sec_13f_provider({"type": "sec_13f", "cik": ""}, _Settings()) is None


def test_build_pads_cik_and_sets_source_id():
    p = build_sec_13f_provider(
        {"type": "sec_13f", "cik": "2045724", "manager_name": "SA LP"}, _Settings())
    assert p is not None
    assert p.cik == "0002045724"
    assert p.source_id == "sec_13f:0002045724"
    assert p.overlay is True


def test_get_text_refuses_non_sec_host():
    with pytest.raises(ValueError):
        _provider()._get_text("https://evil.example.com/x.json")

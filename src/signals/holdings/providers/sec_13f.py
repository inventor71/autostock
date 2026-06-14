"""SEC EDGAR Form 13F-HR provider (F81) — the first HoldingsProvider.

Everything EDGAR-specific and fragile is contained here: finding the latest
13F-HR (incl. ``/A`` amendments, skipping ``13F-NT`` notices), fetching the
INFORMATION TABLE XML, hardened parsing (no XXE / billion-laughs), put/call →
direction normalization, and CUSIP → ticker mapping. It emits a source-agnostic
:class:`HoldingsSnapshot`; the rest of the system never imports this module.

Resilience (FR-8): any HTTP/shape/parse failure raises out of ``fetch_snapshot``
so the daemon refresher records a degraded source — it never returns garbage and
never crashes the turn (the turn path doesn't call this at all).

Network hygiene (NFR-4 / SECURITY-05/11/13): identified User-Agent, paced
requests, host pinned to SEC, all URL components validated by allowlist regex
before they touch a URL, XML size-bounded and DOCTYPE/ENTITY-rejected.
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime

from loguru import logger

from src.signals.holdings.providers.cusip_map import CusipMapper
from src.signals.holdings.records import HoldingRow, HoldingsSnapshot

_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json"
_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{name}"
_ALLOWED_HOSTS = ("data.sec.gov", "www.sec.gov")

_CIK_RE = re.compile(r"^\d{1,10}$")
_ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_XML_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.xml$")
_13F_FORMS = {"13F-HR", "13F-HR/A"}

_MAX_XML_BYTES = 25 * 1024 * 1024  # an information table is well under this
_DEFAULT_UA = "autostock/1.0 (+https://github.com/; contact: ops@example.com)"


# --------------------------------------------------------------------------- #
# Builder (called by the provider registry)
# --------------------------------------------------------------------------- #
def build_sec_13f_provider(entry: dict, settings: object) -> "Sec13FProvider | None":
    """Validate config and construct the provider, or None if the CIK is bad."""
    raw_cik = str(entry.get("cik", "")).strip()
    if not _CIK_RE.match(raw_cik):  # SECURITY-05: reject before it reaches a URL
        logger.warning("holdings/sec_13f: invalid CIK {!r}; skipping", raw_cik)
        return None
    cik10 = raw_cik.zfill(10)
    dh = _disclosed_cfg(settings)
    return Sec13FProvider(
        cik=cik10,
        manager_name=str(entry.get("manager_name") or f"CIK {cik10}"),
        overlay=bool(entry.get("overlay", True)),
        user_agent=str(dh.get("user_agent") or _DEFAULT_UA),
        request_gap_s=float(dh.get("request_gap_s", 0.5) or 0.0),
        connect_timeout=float(dh.get("http_connect_timeout", 3.0)),
        read_timeout=float(dh.get("http_read_timeout", 10.0)),
        map_path=str(dh.get("cusip_map_path") or "config/holdings/cusip_ticker.json"),
    )


def _disclosed_cfg(settings: object) -> dict:
    signals = getattr(settings, "signals", None) or {}
    if isinstance(signals, dict):
        dh = signals.get("disclosed_holdings")
        return dh if isinstance(dh, dict) else {}
    return {}


# --------------------------------------------------------------------------- #
# Provider
# --------------------------------------------------------------------------- #
class Sec13FProvider:
    def __init__(
        self,
        *,
        cik: str,
        manager_name: str,
        overlay: bool = True,
        user_agent: str = _DEFAULT_UA,
        request_gap_s: float = 0.5,
        connect_timeout: float = 3.0,
        read_timeout: float = 10.0,
        map_path: str = "config/holdings/cusip_ticker.json",
    ):
        self.cik = cik
        self.manager_name = manager_name
        self.overlay = overlay
        self.source_id = f"sec_13f:{cik}"
        self._ua = user_agent
        self._gap = request_gap_s
        self._timeout = (connect_timeout, read_timeout)
        self._mapper = CusipMapper(map_path)

    # -- public ---------------------------------------------------------- #
    def fetch_snapshot(self) -> HoldingsSnapshot:
        """Fetch + normalize this CIK's latest 13F-HR holdings (impure)."""
        sub = self._get_json(_SUBMISSIONS_URL.format(cik10=self.cik))
        accession, filing_date = self._latest_13f(sub)
        info_xml = self._fetch_info_table(accession)
        rows, unmapped = self._parse_info_table(info_xml)
        return HoldingsSnapshot(
            source_id=self.source_id,
            manager_name=self.manager_name,
            as_of=filing_date,
            fetched_at=datetime.now(),
            accession=accession,
            rows=rows,
            unmapped_n=unmapped,
        )

    # -- filing selection ------------------------------------------------ #
    def _latest_13f(self, submissions: dict) -> tuple[str, date]:
        recent = ((submissions or {}).get("filings") or {}).get("recent") or {}
        forms = recent.get("form") or []
        accns = recent.get("accessionNumber") or []
        dates = recent.get("filingDate") or []
        best: tuple[date, str] | None = None
        for form, accn, fdate in zip(forms, accns, dates):
            if form not in _13F_FORMS:  # skip 13F-NT (notice, no info table) and others
                continue
            try:
                d = date.fromisoformat(fdate)
            except (TypeError, ValueError):
                continue
            if not _ACCESSION_RE.match(str(accn)):
                continue
            if best is None or d > best[0]:
                best = (d, str(accn))
        if best is None:
            raise ValueError(f"no 13F-HR filing found for CIK {self.cik}")
        return best[1], best[0]

    # -- document fetch -------------------------------------------------- #
    def _fetch_info_table(self, accession: str) -> str:
        acc_nodash = accession.replace("-", "")
        cik_int = str(int(self.cik))
        index = self._get_json(_INDEX_URL.format(cik=cik_int, acc=acc_nodash))
        items = ((index or {}).get("directory") or {}).get("item") or []
        names = [
            str(it.get("name", "")) for it in items
            if isinstance(it, dict) and _XML_NAME_RE.match(str(it.get("name", "")))
        ]
        # primary_doc.xml is the cover page, not the holdings — try the likely info
        # table names first, then any remaining .xml, and accept the first that
        # actually parses as an <informationTable>.
        def _rank(n: str) -> int:
            low = n.lower()
            if low == "primary_doc.xml":
                return 3
            if re.search(r"infotable|form13f|table", low):
                return 0
            return 1

        last_err: Exception | None = None
        for name in sorted(names, key=_rank):
            if name.lower() == "primary_doc.xml":
                continue
            try:
                text = self._get_text(_DOC_URL.format(cik=cik_int, acc=acc_nodash, name=name))
                if "informationTable" in text or "infoTable" in text:
                    return text
            except Exception as exc:  # noqa: BLE001 — try the next candidate
                last_err = exc
        if last_err is not None:
            raise last_err
        raise ValueError(f"no information table in filing {accession} for CIK {self.cik}")

    # -- parsing (hardened) ---------------------------------------------- #
    def _parse_info_table(self, xml_text: str) -> tuple[list[HoldingRow], int]:
        root = _safe_parse_xml(xml_text)
        # Aggregate by (ticker, side); a manager can list one issuer on several lines.
        agg: dict[tuple[str, str], dict] = {}
        total_value = 0.0
        unmapped = 0
        for info in root.iter():
            if _local(info.tag) != "infoTable":
                continue
            fields = {_local(ch.tag): ch for ch in info}
            value = _to_float(_text(fields.get("value")))
            if value is not None:
                total_value += value
            side, put_call = _direction(info, fields)
            cusip = _text(fields.get("cusip"))
            ticker = self._mapper.lookup(cusip) if cusip else None
            if not ticker:
                unmapped += 1
                continue
            shares = _to_int(_shares(fields.get("shrsOrPrnAmt")))
            key = (ticker, side)
            slot = agg.setdefault(
                key, {"value": 0.0, "shares": 0, "raw_id": cusip or "", "put_call": put_call}
            )
            slot["value"] += value or 0.0
            slot["shares"] += shares or 0

        rows: list[HoldingRow] = []
        for (ticker, side), slot in agg.items():
            weight = (slot["value"] / total_value) if total_value > 0 else 0.0
            rows.append(
                HoldingRow(
                    ticker=ticker,
                    side=side,  # type: ignore[arg-type]
                    weight=max(0.0, min(1.0, weight)),
                    value_usd=slot["value"] or None,
                    shares=slot["shares"] or None,
                    raw_id=slot["raw_id"],
                    put_call=slot["put_call"],
                )
            )
        rows.sort(key=lambda r: r.weight, reverse=True)
        return rows, unmapped

    # -- HTTP ------------------------------------------------------------ #
    def _get_json(self, url: str) -> dict:
        import json

        return json.loads(self._get_text(url))

    def _get_text(self, url: str) -> str:
        import requests
        from urllib.parse import urlparse

        host = urlparse(url).hostname or ""
        if host not in _ALLOWED_HOSTS:  # SECURITY-11: pin to SEC, no SSRF
            raise ValueError(f"refusing non-SEC host: {host!r}")
        if self._gap > 0:
            time.sleep(self._gap)  # NFR-4: pace SEC requests
        resp = requests.get(
            url, headers={"User-Agent": self._ua, "Accept-Encoding": "gzip, deflate"},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        if len(resp.content) > _MAX_XML_BYTES:
            raise ValueError(f"SEC document too large ({len(resp.content)} bytes): {url}")
        return resp.text


# --------------------------------------------------------------------------- #
# Module-level pure helpers
# --------------------------------------------------------------------------- #
def _local(tag: str) -> str:
    """Strip an XML namespace: ``{ns}infoTable`` → ``infoTable``."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text(el) -> str | None:
    if el is None:
        return None
    return (el.text or "").strip() or None


def _shares(shrs_el):
    """``shrsOrPrnAmt`` wraps ``sshPrnamt`` (the share/principal count)."""
    if shrs_el is None:
        return None
    for ch in shrs_el:
        if _local(ch.tag) == "sshPrnamt":
            return ch
    return None


def _direction(info_el, fields: dict) -> tuple[str, "str | None"]:
    """Normalize put/call → trade direction. PUT=SHORT(bearish); CALL/none=LONG."""
    pc = (_text(fields.get("putCall")) or "").upper()
    if pc == "PUT":
        return "SHORT", "PUT"
    if pc == "CALL":
        return "LONG", "CALL"
    return "LONG", None


def _to_float(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _to_int(el) -> int | None:
    v = _to_float(_text(el))
    return int(v) if v is not None else None


def _safe_parse_xml(xml_text: str) -> ET.Element:
    """Parse with stdlib ET, but fail closed on DTD/entity tricks (SECURITY-13).

    ElementTree's expat does not resolve *external* entities, but a DOCTYPE with
    internal entity definitions (billion-laughs) is still a DoS vector — reject any
    document that declares one rather than trusting the parser's limits.
    """
    head = xml_text[:4096].upper()
    if "<!DOCTYPE" in head or "<!ENTITY" in head:
        raise ValueError("XML declares a DOCTYPE/ENTITY — refusing to parse")
    return ET.fromstring(xml_text)

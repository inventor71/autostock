"""Finnhub IPO-calendar provider (F78, FR-1).

The aggregate "who lists in the next few days" view comes from Finnhub's free
``/calendar/ipo`` endpoint (date range, one call) — the sibling of the earnings
calendar. Key from env (``FINNHUB_API_KEY``); absence is handled fail-honest by
the collector (calendar simply omitted), never with fabricated data.

Mirrors :mod:`src.signals.sources.finnhub_earnings`: ``requests`` is imported
locally, transport/HTTP errors raise so the collector can degrade, and the parse
is defensive (a malformed entry is skipped, never guessed — SECURITY-05).
"""

from __future__ import annotations

from datetime import date

from loguru import logger

from src.signals.records import IpoRow

_BASE_URL = "https://finnhub.io/api/v1/calendar/ipo"

# Finnhub status strings → our ``IpoRow.status`` Literal.
_STATUS_MAP = {
    "expected": "expected",
    "priced": "priced",
    "withdrawn": "withdrawn",
    "filed": "filed",
}


def _parse_price_range(raw) -> tuple[float | None, float | None]:
    """Parse Finnhub ``price`` ("13.00-15.00" or "135.00" or "") → (low, high)."""
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text:
        return None, None
    parts = text.split("-")
    try:
        vals = [float(p.strip()) for p in parts if p.strip()]
    except (ValueError, TypeError):
        return None, None
    if not vals:
        return None, None
    return min(vals), max(vals)


def _to_float(raw) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _to_int(raw) -> int | None:
    if raw is None:
        return None
    try:
        return int(float(raw))
    except (ValueError, TypeError):
        return None


class FinnhubIpoCalendar:
    """Aggregate IPO calendar over a date range (one HTTP call)."""

    def __init__(
        self,
        api_key: str,
        *,
        http_connect_timeout: float = 3.0,
        http_read_timeout: float = 5.0,
    ):
        if not api_key:
            raise ValueError("FinnhubIpoCalendar requires an api_key")
        self._api_key = api_key
        self._timeout = (http_connect_timeout, http_read_timeout)

    def get_calendar(self, from_date: date, to_date: date) -> list[IpoRow]:
        """IPO entries between ``from_date`` and ``to_date`` (inclusive).

        Raises on transport/HTTP error so the collector can degrade.
        """
        import requests

        params = {
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "token": self._api_key,
        }
        resp = requests.get(_BASE_URL, params=params, timeout=self._timeout)
        resp.raise_for_status()
        payload = resp.json() or {}

        rows: list[IpoRow] = []
        for item in payload.get("ipoCalendar", []) or []:
            if not isinstance(item, dict):
                continue  # unexpected shape — skip (SECURITY-05)
            name = item.get("name")
            date_str = item.get("date")
            if not name or not date_str:
                continue  # name + date are the minimum to be useful
            try:
                ipo_date = date.fromisoformat(str(date_str))
            except (ValueError, TypeError):
                continue
            symbol = item.get("symbol")
            price_low, price_high = _parse_price_range(item.get("price"))
            rows.append(
                IpoRow(
                    name=str(name),
                    symbol=str(symbol).upper() if symbol else None,
                    ipo_date=ipo_date,
                    exchange=str(item["exchange"]) if item.get("exchange") else None,
                    status=_STATUS_MAP.get(str(item.get("status", "")).lower(), "unknown"),
                    shares=_to_int(item.get("numberOfShares")),
                    price_low=price_low,
                    price_high=price_high,
                    est_value=_to_float(item.get("totalSharesValue")),
                )
            )

        logger.debug("Finnhub IPO: {} entries {}..{}", len(rows), from_date, to_date)
        return rows

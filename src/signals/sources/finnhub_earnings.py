"""Finnhub earnings-calendar provider (F61, FR-4).

Alpaca has no earnings calendar, so the aggregate "who reports today/tomorrow"
view comes from Finnhub's free ``/calendar/earnings`` endpoint (date range, one
call). Key from env (``FINNHUB_API_KEY``); absence is handled fail-honest by the
collector (calendar simply omitted), never with fabricated data.
"""

from __future__ import annotations

from datetime import date

from loguru import logger

from src.signals.records import EarningsRow

_BASE_URL = "https://finnhub.io/api/v1/calendar/earnings"

# Finnhub "hour" → our ``when``
_WHEN_MAP = {"bmo": "bmo", "amc": "amc"}


class FinnhubEarningsCalendar:
    """Aggregate earnings calendar over a date range (one HTTP call)."""

    def __init__(
        self,
        api_key: str,
        *,
        http_connect_timeout: float = 3.0,
        http_read_timeout: float = 5.0,
    ):
        if not api_key:
            raise ValueError("FinnhubEarningsCalendar requires an api_key")
        self._api_key = api_key
        self._timeout = (http_connect_timeout, http_read_timeout)

    def get_calendar(self, from_date: date, to_date: date) -> list[EarningsRow]:
        """Earnings entries between ``from_date`` and ``to_date`` (inclusive).

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

        rows: list[EarningsRow] = []
        for item in payload.get("earningsCalendar", []) or []:
            symbol = item.get("symbol")
            date_str = item.get("date")
            if not symbol or not date_str:
                continue
            try:
                earnings_date = date.fromisoformat(str(date_str))
            except (ValueError, TypeError):
                continue
            when = _WHEN_MAP.get(str(item.get("hour", "")).lower(), "unknown")
            eps = item.get("epsEstimate")
            rows.append(
                EarningsRow(
                    symbol=str(symbol).upper(),
                    earnings_date=earnings_date,
                    when=when,
                    eps_estimate=float(eps) if eps is not None else None,
                )
            )

        logger.debug("Finnhub earnings: {} entries {}..{}", len(rows), from_date, to_date)
        return rows

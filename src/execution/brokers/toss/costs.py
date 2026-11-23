"""Account-specific commission refresh and explicitly dated USD simulation costs.

The API schedule is authoritative for commission rates, not for regulatory tax,
rounding or account-specific exemptions. Those are labeled simulation assumptions.
Annual capital-gains tax and FX are deliberately outside this USD ledger.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from src.core.exceptions import BrokerError
from src.execution.brokers.toss import storage

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")
TTL = timedelta(hours=6)
CENT = Decimal("0.01")


def number(value) -> Decimal:
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise ValueError
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise BrokerError("Invalid non-negative cost value") from None


class CommissionSchedule:
    def __init__(self, client, *, clock=None):
        self.client = client
        self.clock = clock or (lambda: datetime.now(UTC))
        identity = hashlib.sha256(
            (client._identity + "\0" + client.credentials.account_seq).encode()
        ).hexdigest()
        self.path = client.state_dir / f"commissions-{identity}.json"

    @staticmethod
    def _select(rows, market: str, now: datetime) -> dict:
        if not isinstance(rows, list):
            raise BrokerError("Invalid Toss commissions response")
        today = now.astimezone(KST).date()
        matches = []
        try:
            for row in rows:
                if row["marketCountry"] != market:
                    continue
                start = date.fromisoformat(row["startDate"]) if row.get("startDate") else date.min
                end = date.fromisoformat(row["endDate"]) if row.get("endDate") else date.max
                rate = number(row["commissionRate"])
                if end < start or rate > 1:
                    raise ValueError
                if start <= today <= end:
                    matches.append((row, rate, end))
        except (KeyError, TypeError, ValueError):
            raise BrokerError("Invalid Toss commission schedule") from None
        if len(matches) != 1:
            raise BrokerError("No unique current Toss commission rate; trading deferred")
        row, rate, end = matches[0]
        # End dates are inclusive in KST. Never overflow the API's 9999-12-31 sentinel.
        expires = (datetime.combine(end + timedelta(days=1), datetime.min.time(), KST)
                   if end != date.max else None)
        return {"market": market, "rate": str(rate), "start_date": row.get("startDate"),
                "end_date": row.get("endDate"),
                "expires_at": expires.isoformat() if expires else None}

    def get(self, market="US", *, force=False) -> dict:
        now = self.clock()
        if now.tzinfo is None:
            raise BrokerError("Commission clock must be timezone-aware")
        with storage.locked(self.path.with_suffix(".lock")):
            now = self.clock()
            cached = storage.read_json(self.path)
            profile = None
            if cached and not force:
                try:
                    fetched = datetime.fromisoformat(cached["fetched_at"])
                    if fetched.tzinfo and timedelta(0) <= now - fetched < TTL:
                        profile = self._select(cached["rows"], market, now)
                except (BrokerError, KeyError, TypeError, ValueError):
                    pass  # Invalid/expired cache is revalidated with the authority.
            if profile is None:
                rows = self.client.request("GET", "/api/v1/commissions", account=True)
                now = self.clock()  # The HTTP request itself may cross the expiry boundary.
                profile = self._select(rows, market, now)
                fetched = now
                storage.write_json(self.path, {"fetched_at": now.isoformat(), "rows": rows})
            next_check = fetched + TTL
            if profile["expires_at"]:
                next_check = min(next_check, datetime.fromisoformat(profile["expires_at"]))
            return {**profile, "confirmed_at": fetched.isoformat(),
                    "next_check_at": next_check.isoformat(), "source": "/api/v1/commissions"}


class TossCosts:
    """Conservative order-total estimates, incrementally charged on partial fills.

Q4 2026 TAF holiday and SEC $20.60/million. The API does not publish these
rates. A bounded review date prevents this assumption silently surviving 2026.
Commission is rounded UP to cents; actual broker rounding may charge less.
The public <=$10 commission waiver is NOT assumed for account-specific promos.
"""
    def __init__(self, schedule: CommissionSchedule):
        self.schedule = schedule

    def profile(self) -> dict:
        commission = self.schedule.get()
        now = self.schedule.clock()
        if not date(2026, 10, 1) <= now.astimezone(ET).date() <= date(2026, 12, 31):
            raise BrokerError("Regulatory cost assumptions need review outside Q4 2026; dry fills paused")
        return {"commission": commission, "sec_sell_rate": "0.0000206",
                "sec_minimum_usd": "0.01", "taf_per_share": "0",
                "regulatory_review_by": "2026-12-31", "rounding": "up_to_cent_per_order",
                "small_order_waiver": "not_assumed_conservative",
                "annual_capital_gains_tax_included": False, "fx_included": False,
                "regulatory_source": "https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2",
                "taf_source": "https://www.govinfo.gov/content/pkg/FR-2026-09-23/html/2026-19392.htm"}

    @staticmethod
    def total(profile: dict, side: str, notional) -> dict:
        value = number(notional)
        commission = (value * number(profile["commission"]["rate"])).quantize(CENT, rounding=ROUND_UP)
        tax = Decimal(0)
        if side == "sell" and value:
            tax = max(CENT, (value * number(profile["sec_sell_rate"])).quantize(CENT, rounding=ROUND_UP))
        return {"commission": float(commission), "regulatory": float(tax),
                "total": float(commission + tax)}

    @staticmethod
    def accrue(profile, side, notional, previous_commission="0", previous_regulatory="0"):
        # A promotion can expire at KST midnight DURING a US session. Charge
        # each partial fill at its applicable rate, never reprice earlier fills.
        value = number(notional)
        basis = number(previous_commission) + value * number(profile["commission"]["rate"])
        tax_basis = number(previous_regulatory)
        if side == "sell":
            tax_basis += value * number(profile["sec_sell_rate"])
        commission = basis.quantize(CENT, rounding=ROUND_UP)
        tax = tax_basis.quantize(CENT, rounding=ROUND_UP)
        return {"commission": float(commission), "regulatory": float(tax),
                "total": float(commission + tax), "commission_basis": str(basis),
                "regulatory_basis": str(tax_basis)}

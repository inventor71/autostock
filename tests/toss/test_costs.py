from datetime import UTC, datetime, timedelta

import httpx
import pytest

from src.core.exceptions import BrokerError
from src.execution.brokers.toss.costs import CommissionSchedule, TossCosts


def test_expiry_midnight_kst_refreshes_and_never_falls_back(client_factory):
    now = [datetime(2026, 11, 24, 14, 59, tzinfo=UTC)]
    rows = [{"marketCountry": "US", "commissionRate": "0.001", "endDate": "2026-11-24"}]
    response = [rows]
    client, calls = client_factory(lambda r: response[0])
    schedule = CommissionSchedule(client, clock=lambda: now[0])
    assert schedule.get()["next_check_at"] == "2026-11-25T00:00:00+09:00"
    assert schedule.get()["rate"] == "0.001"
    assert sum(r.url.path == "/api/v1/commissions" for r in calls) == 1
    now[0] += timedelta(minutes=1)
    # Even a successful response containing the old promotion is unusable.
    with pytest.raises(BrokerError, match="No unique current"):
        schedule.get()
    response[0] = httpx.Response(403)
    with pytest.raises(BrokerError):
        schedule.get()
    response[0] = [{"marketCountry": "US", "commissionRate": "0.0008", "endDate": None}]
    assert schedule.get()["rate"] == "0.0008"
    # A different process reuses the refreshed private cache.
    restarted = CommissionSchedule(client, clock=lambda: now[0])
    assert restarted.get()["rate"] == "0.0008"


@pytest.mark.parametrize("end", [None, "9999-12-31"])
def test_unbounded_schedule_still_refreshes_every_six_hours(client_factory, end):
    now = [datetime(2026, 11, 23, tzinfo=UTC)]
    response = [[{"marketCountry": "US", "commissionRate": "0", "endDate": end}]]
    client, calls = client_factory(lambda r: response[0])
    schedule = CommissionSchedule(client, clock=lambda: now[0])
    assert schedule.get()["rate"] == "0"
    now[0] += timedelta(hours=6)
    response[0] = [{"marketCountry": "US", "commissionRate": "0.002"}]
    assert schedule.get()["rate"] == "0.002"
    assert sum(r.url.path == "/api/v1/commissions" for r in calls) == 2


@pytest.mark.parametrize("rows", [[], {}, [{"marketCountry": "US", "commissionRate": "NaN"}],
    [{"marketCountry": "US", "commissionRate": "-0.001"}],
    [{"marketCountry": "US", "commissionRate": "0.001", "startDate": "2027-01-01"}],
    [{"marketCountry": "US", "commissionRate": "0.001"}] * 2])
def test_invalid_or_ambiguous_rates_fail_closed(client_factory, rows):
    client, _ = client_factory(lambda r: rows)
    with pytest.raises(BrokerError):
        CommissionSchedule(client, clock=lambda: datetime(2026, 11, 23, tzinfo=UTC)).get()


def test_regulatory_costs_are_separate_dated_and_not_capital_gains(client_factory):
    client, _ = client_factory(lambda r: [{"marketCountry": "US", "commissionRate": "0.001"}])
    now = [datetime(2026, 11, 23, tzinfo=UTC)]
    costs = TossCosts(CommissionSchedule(client, clock=lambda: now[0]))
    profile = costs.profile()
    assert not profile["annual_capital_gains_tax_included"]
    assert costs.total(profile, "buy", 1000) == {"commission": 1.0, "regulatory": 0, "total": 1.0}
    assert costs.total(profile, "sell", 1000) == {"commission": 1.0, "regulatory": 0.03, "total": 1.03}
    now[0] = datetime(2027, 1, 2, tzinfo=UTC)
    with pytest.raises(BrokerError, match="review"):
        costs.profile()


def test_http_response_crossing_expiry_cannot_revive_old_rate(client_factory):
    now = [datetime(2026, 11, 24, 14, 59, 59, tzinfo=UTC)]

    def delayed_response(_):
        now[0] += timedelta(seconds=2)
        return [{"marketCountry": "US", "commissionRate": "0.001", "endDate": "2026-11-24"}]

    client, _ = client_factory(delayed_response)
    with pytest.raises(BrokerError, match="No unique current"):
        CommissionSchedule(client, clock=lambda: now[0]).get()

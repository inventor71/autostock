"""F90: AccountFarmBroker tolerates the Broker sandbox TradeAccount schema.

alpaca-py 0.43.x marks last_daytrading_buying_power / last_daytrade_count as Optional-but-required;
the Broker sandbox omits them, so strict parsing raises ValidationError and would crash every
farm-account daemon at boot. _fetch_trade_account keeps the happy path and only falls back to a
raw rebuild (with those keys defaulted to None) on that ValidationError.
"""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from src.execution.brokers import account_farm_broker as m


def _a_validation_error() -> ValidationError:
    class _M(BaseModel):
        x: int

    try:
        _M(x="not-an-int")
    except ValidationError as e:
        return e
    raise AssertionError("expected ValidationError")


def _broker_with_client(client):
    b = object.__new__(m.AccountFarmBroker)  # bypass __init__ (no network/creds)
    b._c = client
    b._account_id = "acc-1"
    return b


def test_fetch_trade_account_happy_path():
    class Client:
        def get_trade_account_by_id(self, aid):
            assert aid == "acc-1"
            return "REAL_ACCT"

        def get(self, path):  # must NOT be reached on the happy path
            raise AssertionError("should not fall back when strict parse succeeds")

    assert _broker_with_client(Client())._fetch_trade_account() == "REAL_ACCT"


def test_fetch_trade_account_falls_back_on_validation_error(monkeypatch):
    err = _a_validation_error()

    class Client:
        def get_trade_account_by_id(self, aid):
            raise err

        def get(self, path):
            assert path == "/trading/accounts/acc-1/account"
            return {"account_number": "271954923"}  # sandbox omits the two daytrade keys

    captured: dict = {}
    monkeypatch.setattr(m, "TradeAccount", lambda **kw: captured.update(kw) or "REBUILT")

    out = _broker_with_client(Client())._fetch_trade_account()
    assert out == "REBUILT"
    assert captured["account_number"] == "271954923"
    assert captured["last_daytrading_buying_power"] is None  # defaulted
    assert captured["last_daytrade_count"] is None            # defaulted

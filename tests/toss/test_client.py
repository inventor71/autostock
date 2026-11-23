import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from src.core.exceptions import BrokerError
from src.execution.brokers.toss.client import API_BASE, TossAPIError, TossClient
from src.execution.brokers.toss.credentials import TossCredentials


def payload(key="intent-1"):
    return {"clientOrderId": key, "symbol": "AAPL", "quantity": "1", "side": "BUY", "orderType": "MARKET"}


def test_two_clients_share_token_and_scope_account_header(client_factory):
    first, calls1 = client_factory(lambda r: [])
    second, calls2 = client_factory(lambda r: [])
    first.accounts()
    second.request("GET", "/api/v1/holdings", account=True)
    assert [r.url.path for r in calls1] == ["/oauth2/token", "/api/v1/accounts"]
    assert [r.url.path for r in calls2] == ["/api/v1/holdings"]
    assert "X-Tossinvest-Account" not in calls1[-1].headers
    assert calls2[-1].headers["X-Tossinvest-Account"] == "1"
    assert calls2[-1].headers["Authorization"] == "Bearer test-access"
    assert b"grant_type=client_credentials" in calls1[0].content


def test_concurrent_clients_do_not_revoke_each_others_tokens(client_factory):
    first, a = client_factory(lambda r: [])
    second, b = client_factory(lambda r: [])
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda c: c.accounts(), [first, second])) == [[], []]
    assert sum(r.url.path == "/oauth2/token" for r in a + b) == 1


def test_revoked_token_refreshes_once_without_leaking_request(tmp_path, credentials):
    calls = []

    def route(request):
        calls.append(request)
        if request.url.path == "/oauth2/token":
            n = sum(r.url.path == "/oauth2/token" for r in calls)
            return httpx.Response(200, json={"access_token": f"token-{n}", "expires_in": 1000})
        if request.headers["Authorization"] == "Bearer token-1":
            return httpx.Response(401, json={"error": {"code": "token-revoked"}})
        return httpx.Response(200, json={"result": []})

    with TossClient(credentials, state_dir=tmp_path / "tokens", http=httpx.Client(transport=httpx.MockTransport(route))) as client:
        assert client.accounts() == []
    assert len(calls) == 4


@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_read_only_rejects_every_mutation_before_auth(client_factory, method):
    client, calls = client_factory(lambda r: pytest.fail("Must not hit HTTP"))
    with pytest.raises(BrokerError, match="read-only"):
        client.request(method, "/api/v1/orders", account=True)
    assert calls == []


def test_reads_retry_rate_limits_but_mutations_do_not(client_factory, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda n: None)
    tries = 0

    def route(request):
        nonlocal tries
        tries += 1
        if tries == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {"code": "rate-limit-exceeded"}})
        return []

    client, _ = client_factory(route)
    assert client.accounts() == []
    assert tries == 2
    write, calls = client_factory(lambda r: httpx.Response(503), read_only=False)
    with pytest.raises(TossAPIError):
        write.create_order(payload())
    assert sum(r.method == "POST" and r.url.path == "/api/v1/orders" for r in calls) == 1


def test_long_retry_after_fails_instead_of_retrying_early(client_factory):
    client, calls = client_factory(lambda r: httpx.Response(429, headers={"Retry-After": "300"}))
    with pytest.raises(TossAPIError):
        client.accounts()
    assert len(calls) == 2


def test_unknown_submission_survives_restart_without_duplicate(client_factory):
    def timeout(request):
        raise httpx.ReadTimeout("error reflecting test-secret test-access", request=request)

    first, calls = client_factory(timeout, read_only=False)
    with pytest.raises(BrokerError) as caught:
        first.create_order(payload())
    assert "test-secret" not in str(caught.value)
    assert "test-access" not in str(caught.value)
    second, other = client_factory(lambda r: pytest.fail("Unresolved submission must not retry"), read_only=False)
    with pytest.raises(BrokerError, match="unresolved"):
        second.create_order(payload())
    assert sum(r.url.path == "/api/v1/orders" for r in calls) == 1
    assert other == []


def test_successful_submission_is_not_repeated_after_server_key_expiry(client_factory, monkeypatch):
    client, calls = client_factory(lambda r: {"orderId": "accepted-1"}, read_only=False)
    assert client.create_order(payload())["orderId"] == "accepted-1"
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + 3600)
    assert client.create_order(payload())["orderId"] == "accepted-1"
    assert sum(r.url.path == "/api/v1/orders" for r in calls) == 1
    with pytest.raises(BrokerError, match="different order"):
        client.create_order({**payload(), "quantity": "2"})


def test_order_ids_scoped_to_account(client_factory):
    a, calls1 = client_factory(lambda r: {"orderId": "a"}, read_only=False)
    b, calls2 = client_factory(lambda r: {"orderId": "b"}, read_only=False,
                               creds=TossCredentials("test-client", "test-secret", "2"))
    assert a.create_order(payload())["orderId"] == "a"
    assert b.create_order(payload())["orderId"] == "b"
    assert calls1[-1].headers["X-Tossinvest-Account"] == "1"
    assert calls2[-1].headers["X-Tossinvest-Account"] == "2"


def test_unsafe_response_messages_are_not_in_errors(client_factory):
    client, _ = client_factory(lambda r: httpx.Response(403, json={"error": {
        "code": "ip-not-allowed", "message": "test-secret test-access", "data": {"secret": "test-secret"},
    }}))
    with pytest.raises(TossAPIError) as caught:
        client.accounts()
    assert "ip-not-allowed" in str(caught.value)
    assert "test-secret" not in str(caught.value)
    assert "test-access" not in str(caught.value)


def test_unrecognized_error_code_cannot_echo_a_secret(client_factory):
    client, _ = client_factory(lambda r: httpx.Response(403, json={"error": {"code": "test-secret"}}))
    with pytest.raises(TossAPIError) as caught:
        client.accounts()
    assert "test-secret" not in str(caught.value)
    assert caught.value.code == "request-failed"


def test_redirect_does_not_forward_credentials(tmp_path, credentials):
    seen = []

    def redirect(request):
        seen.append(str(request.url))
        return httpx.Response(307, headers={"Location": "https://wrong.example/oauth2/token"})

    with TossClient(credentials, state_dir=tmp_path / "state", http=httpx.Client(
        transport=httpx.MockTransport(redirect), follow_redirects=True,
    )) as client, pytest.raises(TossAPIError):
        client.accounts()
    assert seen == [API_BASE + "/oauth2/token"]


def test_paginated_history_is_complete_and_repeated_cursor_fails(client_factory):
    def route(request):
        if request.url.params.get("cursor") == "next":
            return {"orders": [{"orderId": "second"}], "nextCursor": None, "hasNext": False}
        return {"orders": [{"orderId": "first"}], "nextCursor": "next", "hasNext": True}

    client, _ = client_factory(route)
    assert len(client.pages("/api/v1/orders", "orders", params={"status": "CLOSED"})) == 2
    broken, _ = client_factory(lambda r: {"orders": [], "hasNext": True, "nextCursor": "same"})
    with pytest.raises(BrokerError, match="pagination"):
        broken.pages("/api/v1/orders", "orders")

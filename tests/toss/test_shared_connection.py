import json
import time

import httpx
import pytest

from config.config import Settings
from src.core.exceptions import BrokerError
from src.execution.brokers.factory import create_toss_client
from src.execution.brokers.toss import setup, storage
from src.execution.brokers.toss.client import TossClient
from src.execution.brokers.toss.credentials import (
    TossCredentials,
    load_credentials,
    save_credentials,
)


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "toss-stock"
    storage.write_json(root / ".cache/token.json", {
        "access_token": "external-token", "expires_at": time.time() + 3600,
    })
    return root


def shared(source, account="7"):
    return TossCredentials(account_seq=account, shared_token_file=str(source / ".cache/token.json"))


def test_link_uses_existing_account_without_reading_env_or_copying_secrets(source, tmp_path, monkeypatch, capsys):
    path = tmp_path / "autostock/credentials.json"
    storage.write_json(source / ".cache/account.json", {"accountSeq": 7})
    # A directory cannot be read as an env file. Linking must never try to load it.
    (source / ".env").mkdir()
    calls = []

    def route(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer external-token"
        if request.url.path == "/api/v1/accounts":
            return httpx.Response(200, json={"result": [
                {"accountType": "BROKERAGE", "accountSeq": 8, "accountNo": "00000000008"},
                {"accountType": "BROKERAGE", "accountSeq": 7, "accountNo": "12345678901"},
            ]})
        assert request.headers["X-Tossinvest-Account"] == "7"
        return httpx.Response(200, json={"result": {}})

    monkeypatch.setattr(setup, "TossClient", lambda creds: TossClient(
        creds, state_dir=tmp_path / "unused-state", http=httpx.Client(transport=httpx.MockTransport(route)),
    ))
    monkeypatch.setattr(setup.getpass, "getpass", lambda _: pytest.fail("Must not ask for keys"))
    argv = ["--from-toss-stock", str(source), "--credentials-file", str(path)]
    before = (source / ".cache/token.json").read_bytes()
    assert setup.main(argv) == 0
    assert load_credentials(path) == shared(source)
    assert json.loads(path.read_text()) == {
        "shared_token_file": str(source / ".cache/token.json"), "account_seq": "7",
    }
    assert path.stat().st_mode & 0o777 == 0o600
    assert (source / ".cache/token.json").read_bytes() == before
    assert not (tmp_path / "unused-state").exists()
    assert setup.main(["--check", "--credentials-file", str(path)]) == 0
    assert len(calls) == 6
    output = capsys.readouterr().out
    assert "external-token" not in output and "12345678901" not in output
    assert "No keys or tokens were copied" in output


@pytest.mark.parametrize("selection,count,expected", [(None, 1, 0), (None, 2, 1), (9, 1, 1)])
def test_link_account_selection_and_failed_link_preserves_previous(source, tmp_path, monkeypatch, selection, count, expected):
    path = tmp_path / "autostock/credentials.json"
    original = TossCredentials("original-client", "original-secret", "1")
    save_credentials(original, path)
    if selection is not None:
        storage.write_json(source / ".cache/account.json", {"accountSeq": selection})

    def route(request):
        assert request.method == "GET"
        result = [
            {"accountType": "BROKERAGE", "accountSeq": 7 + n, "accountNo": "00000000007"}
            for n in range(count)
        ] if request.url.path == "/api/v1/accounts" else {}
        return httpx.Response(200, json={"result": result})

    monkeypatch.setattr(setup, "TossClient", lambda creds: TossClient(
        creds, http=httpx.Client(transport=httpx.MockTransport(route)),
    ))
    assert setup.main(["--from-toss-stock", str(source), "--credentials-file", str(path)]) == expected
    assert load_credentials(path) == (original if expected else shared(source))


def test_shared_reads_follow_rotation_without_local_cache_or_token_issuance(source, tmp_path, client_factory):
    credentials = shared(source)
    client, calls = client_factory(lambda _: [], creds=credentials)
    assert client.accounts() == []
    storage.write_json(source / ".cache/token.json", {
        "access_token": "rotated-token", "expires_at": time.time() + 3600,
    })
    assert client.accounts() == []
    assert [r.headers["Authorization"] for r in calls] == ["Bearer external-token", "Bearer rotated-token"]
    assert all(r.method == "GET" for r in calls)
    assert not (tmp_path / "state").exists()
    assert "external-token" not in repr(credentials)


@pytest.mark.parametrize("fault", ["missing", "expired", "empty", "corrupt", "nonfinite", "invalid-token", "permissions", "symlink"])
def test_invalid_shared_token_never_falls_back_to_issuing_one(source, tmp_path, client_factory, fault):
    path = source / ".cache/token.json"
    if fault == "missing":
        path.unlink()
    elif fault == "expired":
        storage.write_json(path, {"access_token": "private-token", "expires_at": time.time() - 1})
    elif fault == "empty":
        storage.write_json(path, {})
    elif fault == "corrupt":
        path.write_text("private-invalid-json")
    elif fault == "nonfinite":
        storage.write_json(path, {"access_token": "private-token", "expires_at": float("inf")})
    elif fault == "invalid-token":
        storage.write_json(path, {"access_token": "private\ninvalid", "expires_at": time.time() + 1000})
    elif fault == "permissions":
        path.chmod(0o644)
    elif fault == "symlink":
        actual = path.with_name("actual.json")
        path.rename(actual)
        path.symlink_to(actual)
    client, calls = client_factory(lambda _: pytest.fail("Must not call HTTP"), creds=shared(source))
    with pytest.raises(BrokerError) as caught:
        client.accounts()
    assert "private-token" not in str(caught.value)
    assert "private-invalid-json" not in str(caught.value)
    assert calls == []
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("rotate", [False, True])
def test_rejected_shared_token_only_retries_if_owner_has_rotated_it(source, client_factory, rotate):
    def route(request):
        if request.headers["Authorization"] == "Bearer external-token":
            if rotate:
                storage.write_json(source / ".cache/token.json", {
                    "access_token": "new-token", "expires_at": time.time() + 3600,
                })
            return httpx.Response(401, json={"error": {"code": "token-revoked"}})
        return []

    client, calls = client_factory(route, creds=shared(source))
    if rotate:
        assert client.accounts() == []
    else:
        with pytest.raises(BrokerError, match="toss-stock"):
            client.accounts()
    assert len(calls) == (2 if rotate else 1)
    assert all(r.method == "GET" for r in calls)


def test_shared_connection_cannot_enable_writes_via_config_or_attribute(source, tmp_path, client_factory):
    path = tmp_path / "autostock/credentials.json"
    save_credentials(shared(source), path)
    settings = Settings(_env_file=None, app={"mode": "live"}, toss={
        "credentials_file": str(path), "read_only": False,
    })
    with pytest.raises(BrokerError, match="read-only"):
        create_toss_client(settings)
    client, calls = client_factory(lambda _: pytest.fail("Must not call HTTP"), creds=shared(source))
    client.read_only = False
    for method in ("POST", "DELETE"):
        with pytest.raises(BrokerError, match="read-only"):
            client.request(method, "/api/v1/orders", account=True)
    with pytest.raises(BrokerError, match="read-only"):
        client.create_order({"clientOrderId": "attempt"})
    assert calls == []
    assert not (tmp_path / "state").exists()


def test_shared_credentials_cannot_mix_modes_or_use_relative_paths(source):
    with pytest.raises(BrokerError, match="not both"):
        TossCredentials("client", "secret", shared_token_file=str(source / ".cache/token.json"))
    with pytest.raises(BrokerError, match="absolute path"):
        TossCredentials(shared_token_file=".cache/token.json")
    with pytest.raises(BrokerError):
        TossCredentials()

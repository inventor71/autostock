
import pytest

from src.core.exceptions import BrokerError
from src.execution.brokers.toss import setup, storage
from src.execution.brokers.toss.credentials import (
    TossCredentials,
    credential_path,
    load_credentials,
    save_credentials,
)


def test_private_storage_and_safe_representations(tmp_path, credentials):
    path = tmp_path / "private/credentials.json"
    save_credentials(credentials, path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert load_credentials(path) == credentials
    assert "test-secret" not in repr(credentials)
    assert "test-client" not in repr(credentials)


def test_credential_default_is_outside_repository(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert credential_path() == tmp_path / "autostock/toss/credentials.json"


def test_insecure_file_and_symlinks_fail_closed(tmp_path, credentials):
    path = tmp_path / "private/credentials.json"
    save_credentials(credentials, path)
    path.chmod(0o644)
    with pytest.raises(BrokerError, match="0600"):
        load_credentials(path)
    path.chmod(0o600)
    link = path.parent / "link.json"
    link.symlink_to(path)
    with pytest.raises(BrokerError):
        load_credentials(link)
    with pytest.raises(BrokerError, match="symlink"):
        save_credentials(credentials, link)


def test_insecure_directory_cannot_store_tokens(tmp_path):
    path = tmp_path / "public"
    path.mkdir(mode=0o755)
    with pytest.raises(BrokerError, match="0700"):
        storage.write_json(path / "token.json", {"access_token": "private"})


def test_corrupt_storage_not_overwritten_with_new_orders(tmp_path):
    path = tmp_path / "private/value.json"
    storage.write_json(path, {})
    path.write_text("invalid secret value")
    with pytest.raises(BrokerError, match="invalid") as caught:
        storage.read_json(path)
    assert "secret value" not in str(caught.value)


def test_setup_requires_terminal_and_does_not_read_piped_keys(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(setup.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(setup.getpass, "getpass", lambda p: pytest.fail("No hidden input without tty"))
    path = tmp_path / "private/credentials.json"
    assert setup.main(["--credentials-file", str(path)]) == 1
    assert not path.exists()
    assert "terminal" in capsys.readouterr().err


def test_setup_verifies_then_saves_without_trading(tmp_path, monkeypatch, capsys):
    path = tmp_path / "private/credentials.json"
    monkeypatch.setattr(setup.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(setup.sys.stderr, "isatty", lambda: True)
    values = iter(["my-client", "my-secret"])
    monkeypatch.setattr(setup.getpass, "getpass", lambda p: next(values))
    calls = []

    class Client:
        def __init__(self, credentials): self.credentials = credentials
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def accounts(self):
            return [{"accountType": "BROKERAGE", "accountSeq": 7, "accountNo": "12345678901"}]
        def request(self, method, path, **kwargs):
            calls.append((method, path))
            assert self.credentials.account_seq == "7"
            return {}

    monkeypatch.setattr(setup, "TossClient", Client)
    assert setup.main(["--credentials-file", str(path)]) == 0
    assert load_credentials(path).account_seq == "7"
    assert calls == [("GET", "/api/v1/holdings"), ("GET", "/api/v1/buying-power")]
    output = capsys.readouterr().out
    assert all(secret not in output for secret in ["my-client", "my-secret", "12345678901"])
    assert "8901" in output
    assert "trading permissions were not changed" in output


def test_invalid_account_does_not_overwrite_existing_credentials(tmp_path, monkeypatch):
    path = tmp_path / "private/credentials.json"
    save_credentials(TossCredentials("original", "original-secret", "1"), path)
    monkeypatch.setattr(setup.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(setup.sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr(setup.getpass, "getpass", lambda p: "new-value")

    class Client:
        def __init__(self, credentials): self.credentials = credentials
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def accounts(self): return []

    monkeypatch.setattr(setup, "TossClient", Client)
    assert setup.main(["--credentials-file", str(path)]) == 1
    assert load_credentials(path).client_id == "original"


def test_no_secrets_as_cli_arguments():
    with pytest.raises(SystemExit):
        setup.main(["--client-secret", "not-a-real-key"])

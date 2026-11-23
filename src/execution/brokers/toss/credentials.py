"""Credentials are read lazily, never included in Settings dumps or reprs."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.core.exceptions import BrokerError
from src.execution.brokers.toss import storage


@dataclass(frozen=True)
class TossCredentials:
    client_id: str = field(default="", repr=False)
    client_secret: str = field(default="", repr=False)
    account_seq: str = field(default="", repr=False)
    shared_token_file: str = field(default="", repr=False)

    def __post_init__(self):
        if not isinstance(self.shared_token_file, str):
            raise BrokerError("Toss shared token file must be an absolute path")
        if self.shared_token_file:
            if self.client_id or self.client_secret:
                raise BrokerError("Use either a shared Toss token or client credentials, not both")
            if not Path(self.shared_token_file).is_absolute():
                raise BrokerError("Toss shared token file must be an absolute path")
        else:
            for value in (self.client_id, self.client_secret):
                if not isinstance(value, str) or not value or value != value.strip() or any(c.isspace() for c in value):
                    raise BrokerError("Toss client ID and secret must be nonempty without whitespace")
        if self.account_seq and (not self.account_seq.isascii() or not self.account_seq.isdigit()):
            raise BrokerError("Toss account selection must be a numeric accountSeq")


def credential_path(path: str | Path | None = None) -> Path:
    return Path(path).expanduser() if path else storage.config_dir() / "credentials.json"


def load_credentials(path: str | Path | None = None, *, require_account: bool = True):
    target = credential_path(path)
    value = storage.read_json(target)
    if not value:
        raise BrokerError("Toss account is not linked; run python -m src.execution.brokers.toss.setup")
    try:
        result = TossCredentials(
            client_id=value.get("client_id", ""), client_secret=value.get("client_secret", ""),
            account_seq=str(value.get("account_seq", "")),
            shared_token_file=value.get("shared_token_file", ""),
        )
    except (KeyError, TypeError, AttributeError):
        raise BrokerError("Toss credential file is incomplete; run Toss setup again") from None
    if require_account and not result.account_seq:
        raise BrokerError("No Toss account selected; run Toss setup again")
    return result


def save_credentials(credentials: TossCredentials, path: str | Path | None = None):
    value = {"account_seq": credentials.account_seq}
    if credentials.shared_token_file:
        value["shared_token_file"] = credentials.shared_token_file
    else:
        value.update(client_id=credentials.client_id, client_secret=credentials.client_secret)
    storage.write_json(credential_path(path), value)

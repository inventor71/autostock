"""Credentials are read lazily, never included in Settings dumps or reprs."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.core.exceptions import BrokerError
from src.execution.brokers.toss import storage


@dataclass(frozen=True)
class TossCredentials:
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    account_seq: str = field(default="", repr=False)

    def __post_init__(self):
        for value in (self.client_id, self.client_secret):
            if not value or value != value.strip() or any(c.isspace() for c in value):
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
            client_id=value["client_id"], client_secret=value["client_secret"],
            account_seq=str(value.get("account_seq", "")),
        )
    except (KeyError, TypeError, AttributeError):
        raise BrokerError("Toss credential file is incomplete; run Toss setup again") from None
    if require_account and not result.account_seq:
        raise BrokerError("No Toss account selected; run Toss setup again")
    return result


def save_credentials(credentials: TossCredentials, path: str | Path | None = None):
    storage.write_json(credential_path(path), {
        "client_id": credentials.client_id, "client_secret": credentials.client_secret,
        "account_seq": credentials.account_seq,
    })

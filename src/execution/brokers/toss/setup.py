"""Local terminal account linking; never accepts secrets in command arguments."""
from __future__ import annotations

import argparse
import getpass
import sys
from dataclasses import replace
from pathlib import Path

from src.core.exceptions import BrokerError
from src.execution.brokers.toss.client import TossClient
from src.execution.brokers.toss.credentials import (
    TossCredentials,
    credential_path,
    load_credentials,
    save_credentials,
)


def _accounts(client: TossClient) -> list[dict]:
    accounts = [a for a in client.accounts() if a["accountType"] == "BROKERAGE"]
    if not accounts:
        raise BrokerError("No eligible Toss BROKERAGE account was returned")
    return accounts


def _verify(client: TossClient, accounts: list[dict]) -> None:
    account = next((a for a in accounts if str(a["accountSeq"]) == client.credentials.account_seq), None)
    if account is None:
        raise BrokerError("The selected Toss account is no longer available; run setup again")
    client.request("GET", "/api/v1/holdings", account=True)
    client.request("GET", "/api/v1/buying-power", params={"currency": "USD"}, account=True)
    print(f"Read-only access verified for account ending {str(account['accountNo'])[-4:]}.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Link Toss locally without enabling trading")
    parser.add_argument("--check", action="store_true", help="Verify the saved account; no trading")
    parser.add_argument("--credentials-file", type=Path, help="Private file outside the repository")
    args = parser.parse_args(argv)
    path = credential_path(args.credentials_file)
    try:
        # Keys belong outside all worktree/repository files, even if a caller
        # overrides the default. Gitignore alone is not the credential boundary.
        if any((parent / ".git").exists() for parent in path.resolve().parents):
            raise BrokerError("Store Toss credentials outside the repository")
        if args.check:
            with TossClient(load_credentials(path)) as client:
                _verify(client, _accounts(client))
            return 0
        if not sys.stdin.isatty() or not sys.stderr.isatty():
            raise BrokerError("Run setup in your own terminal; credentials require hidden interactive input")
        print("In Toss Securities WTS → Settings → Open API:")
        print("issue a client ID/secret and register this machine's public IP.")
        print("Paste the values below. Input is hidden; trading stays disabled.")
        credentials = TossCredentials(
            getpass.getpass("Client ID (hidden): ").strip(),
            getpass.getpass("Client secret (hidden): ").strip(),
        )
        with TossClient(credentials) as client:
            accounts = _accounts(client)
            for i, account in enumerate(accounts, 1):
                print(f"{i}. Brokerage account ending {str(account['accountNo'])[-4:]}")
            if len(accounts) == 1:
                selected = accounts[0]
            else:
                choice = input("Choose account number from this list: ").strip()
                if not choice.isdigit() or not 1 <= int(choice) <= len(accounts):
                    raise BrokerError("Invalid account selection; credentials were not saved")
                selected = accounts[int(choice) - 1]
            credentials = replace(credentials, account_seq=str(selected["accountSeq"]))
            client.credentials = credentials
            _verify(client, accounts)
        save_credentials(credentials, path)
        print(f"Saved privately at {path} (permissions 0600).")
        print("Account linked. Autostock configuration and trading permissions were not changed.")
        return 0
    except (BrokerError, OSError, KeyError, TypeError, ValueError):
        # BrokerError messages are deliberately sanitized at the network/storage
        # boundary. Other exceptions must not dump HTTP requests or local values.
        error = sys.exc_info()[1]
        print(str(error) if isinstance(error, BrokerError) else "Cannot access private Toss storage.", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nSetup canceled; credentials were not saved.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

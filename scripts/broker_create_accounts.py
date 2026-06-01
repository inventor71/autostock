#!/usr/bin/env python
"""Broker API (sandbox) account farm — create / list simulated trading accounts.

This is intentionally *separate* from the bot's Trading API integration:
  - Trading API  (TradingClient)  → APCA-API-KEY-ID / SECRET, one "my" account.
  - Broker  API  (BrokerClient)   → Basic auth (broker key:secret), N accounts
                                     addressed by account_id, sandbox = all simulated.

Sandbox is free and needs no business agreement, so an individual can spin up as
many simulated ("paper-equivalent") accounts as they like.

Usage:
  venv/bin/python scripts/broker_create_accounts.py --count 3
  venv/bin/python scripts/broker_create_accounts.py --list

Reads BROKER_API_KEY / BROKER_API_SECRET from the environment (.env). Grab those
from the Broker dashboard's *sandbox* API key section — they are NOT your Trading
API keys.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

from alpaca.broker.client import BrokerClient
from alpaca.broker.requests import (
    CreateAccountRequest,
    CreateACHRelationshipRequest,
    CreateACHTransferRequest,
)
from alpaca.broker.models import Contact, Identity, Disclosures, Agreement
from alpaca.broker.enums import (
    AgreementType,
    TaxIdType,
    FundingSource,
    BankAccountType,
    TransferDirection,
    TransferTiming,
)


def _client() -> BrokerClient:
    load_dotenv()
    key = os.getenv("BROKER_API_KEY")
    secret = os.getenv("BROKER_API_SECRET")
    if not key or not secret:
        sys.exit(
            "Missing BROKER_API_KEY / BROKER_API_SECRET in env.\n"
            "Add your *sandbox* broker keys to .env (see .env.example)."
        )
    # sandbox=True → broker-api.sandbox.alpaca.markets, everything simulated.
    return BrokerClient(api_key=key, secret_key=secret, sandbox=True)


def _dummy_account(email: str, seed: int) -> CreateAccountRequest:
    """Minimal KYC fixture that the sandbox auto-approves.

    `seed` makes the SSN unique per account. SSN rules the sandbox enforces:
    area != 000/666 and not 900-999, group != 00, serial != 0000.
    """
    now = datetime.now(timezone.utc).isoformat()
    ip = "127.0.0.1"
    serial = seed % 9999 + 1          # 0001-9999, never 0000
    tax_id = f"234-56-{serial:04d}"   # area 234 / group 56 are always valid
    return CreateAccountRequest(
        contact=Contact(
            email_address=email,
            phone_number="+15556667788",
            street_address=["20 N San Mateo Dr"],
            city="San Mateo",
            state="CA",
            postal_code="94401",
            country="USA",
        ),
        identity=Identity(
            given_name="Auto",
            family_name="Stock",
            date_of_birth="1990-01-01",
            tax_id=tax_id,
            tax_id_type=TaxIdType.USA_SSN,
            country_of_citizenship="USA",
            country_of_birth="USA",
            country_of_tax_residence="USA",
            funding_source=[FundingSource.EMPLOYMENT_INCOME],
        ),
        disclosures=Disclosures(
            is_control_person=False,
            is_affiliated_exchange_or_finra=False,
            is_politically_exposed=False,
            immediate_family_exposed=False,
        ),
        agreements=[
            Agreement(
                agreement=AgreementType.CUSTOMER,
                signed_at=now,
                ip_address=ip,
            ),
            Agreement(
                agreement=AgreementType.ACCOUNT,
                signed_at=now,
                ip_address=ip,
            ),
        ],
    )


def cmd_create(client: BrokerClient, count: int, prefix: str) -> None:
    stamp = int(time.time())
    created = []
    for i in range(count):
        # Unique email per account; sandbox rejects duplicates with 409.
        email = f"{prefix}+{stamp}-{i}@example.com"
        try:
            acct = client.create_account(_dummy_account(email, stamp + i))
        except Exception as e:  # noqa: BLE001 — surface the API error verbatim
            print(f"  ✗ {email}: {e}")
            continue
        created.append(acct)
        print(f"  ✓ {email}")
        print(f"      account_id = {acct.id}")
        print(f"      number     = {acct.account_number}   status = {acct.status}")
    print(f"\nCreated {len(created)}/{count} sandbox accounts.")
    if created:
        print("Trade against them via BrokerClient + account_id "
              "(e.g. submit_order_for_account / get_trade_account_by_id).")


def cmd_fund(client: BrokerClient, account_id: str | None, amount: float) -> None:
    """Add simulated buying power to sandbox accounts via ACH deposit.

    Sandbox accounts start with $0 buying power.  This creates a dummy ACH
    relationship and an INCOMING transfer; the sandbox processes it who-knows-
    how-fast (V3 — not assumed instant).
    """
    accounts = client.list_accounts()
    targets: list[str] = [account_id] if account_id else [str(a.id) for a in accounts]
    if not targets:
        print("No accounts to fund.")
        return

    for aid in targets:
        acct = client.get_trade_account_by_id(aid)
        print(f"  funding {acct.account_number} ({aid[:8]}…): ${amount:,.0f}")
        try:
            # Step 1: reuse existing ACH relationship, or create one.
            rels = client.get_ach_relationships_for_account(aid)
            if rels:
                rel_id = str(rels[0].id)
            else:
                rel = client.create_ach_relationship_for_account(
                    aid,
                    CreateACHRelationshipRequest(
                        account_owner_name="Auto Stock",
                        bank_account_type=BankAccountType.CHECKING,
                        bank_account_number="123456789",
                        bank_routing_number="021000021",
                        nickname="sandbox-funding",
                    ),
                )
                rel_id = str(rel.id)
            # Step 2: transfer
            tx = client.create_transfer_for_account(
                aid,
                CreateACHTransferRequest(
                    relationship_id=rel_id,
                    amount=str(int(amount)),
                    direction=TransferDirection.INCOMING,
                    timing=TransferTiming.IMMEDIATE,
                ),
            )
            # Re-read
            acct2 = client.get_trade_account_by_id(aid)
            print(
                f"    transfer {str(tx.id)[:8]}… → "
                f"buying_power=${float(acct2.buying_power):,.2f}"
            )
        except Exception as e:
            print(f"    ✗ {e}")

def cmd_list(client: BrokerClient) -> None:
    accounts = client.list_accounts()
    if not accounts:
        print("No accounts in this sandbox.")
        return
    print(f"{len(accounts)} account(s):")
    for a in accounts:
        print(f"  {a.id}  {a.account_number}  {a.status}  {getattr(a, 'email', '')}")


def main() -> None:
    p = argparse.ArgumentParser(description="Alpaca Broker sandbox account farm")
    p.add_argument("--count", type=int, default=1, help="how many accounts to create")
    p.add_argument("--prefix", default="autostock", help="email local-part prefix")
    p.add_argument("--list", action="store_true", help="list existing accounts and exit")
    p.add_argument("--fund", type=float, metavar="AMOUNT",
                   help="fund account(s) with $AMOUNT via ACH (sandbox)")
    p.add_argument("--account", help="target account_id for --fund (omit = all)")
    args = p.parse_args()

    client = _client()
    if args.fund:
        cmd_fund(client, args.account, args.fund)
    elif args.list:
        cmd_list(client)
    else:
        cmd_create(client, args.count, args.prefix)


if __name__ == "__main__":
    main()

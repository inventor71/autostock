"""Bounded HTTPS transport for the public Toss Securities REST API.

One token is valid per client, so every process shares a locked token cache.
Only GETs retry automatically. Order creates have a durable intent record: an
ambiguous response is reconciled by the operator, never blindly sent again.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from pathlib import Path

import httpx

from src.core.exceptions import BrokerError
from src.execution.brokers.toss import storage
from src.execution.brokers.toss.credentials import TossCredentials

API_BASE = "https://openapi.tossinvest.com"
_ERROR_CODES = frozenset({
    "invalid_client", "invalid_request", "invalid-request", "order-not-found",
    "token-revoked", "token-expired", "ip-not-allowed", "edge-blocked",
    "insufficient-buying-power", "insufficient-sellable-quantity", "order-hours-closed",
    "rate-limit-exceeded", "edge-rate-limit-exceeded", "request-in-progress",
    "idempotency-key-conflict", "account-restricted", "prerequisite-required",
    "stock-not-found", "confirm-high-value-required", "us-modify-quantity-not-supported",
    "modify-restricted", "cancel-restricted", "internal-error", "maintenance",
})


class TossAPIError(BrokerError):
    def __init__(self, status: int, code: str):
        self.status = status
        self.code = code
        hints = {
            "invalid_client": "Check the client ID and secret in Toss WTS.",
            "ip-not-allowed": "Register this machine's public IP in Toss WTS.",
            "insufficient-buying-power": "Check available cash; Toss API does not auto-convert FX.",
        }
        hint = hints.get(code, "")
        if status == 403 and not hint:
            hint = "Check the allowed public IP and OpenAPI access in Toss WTS."
        super().__init__(f"Toss API HTTP {status} ({code}). {hint}".strip())


def _api_error(response: httpx.Response) -> TossAPIError:
    # Deliberately omit arbitrary response messages, bodies, headers and request
    # objects: proxies and upstream errors can reflect secrets back to callers.
    code = "request-failed"
    try:
        body = response.json()
        error = body.get("error", body) if isinstance(body, dict) else {}
        candidate = error if isinstance(error, str) else error.get("code", "request-failed")
        if isinstance(candidate, str) and candidate in _ERROR_CODES:
            code = candidate
    except (ValueError, AttributeError):
        pass
    return TossAPIError(response.status_code, code)


class TossClient:
    def __init__(
        self, credentials: TossCredentials, *, read_only: bool = True,
        state_dir: Path | str | None = None, http: httpx.Client | None = None,
    ):
        if credentials.shared_token_file and not read_only:
            raise BrokerError("Shared Toss tokens are read-only in Autostock")
        self.credentials = credentials
        self.read_only = read_only
        self.state_dir = Path(state_dir) if state_dir is not None else storage.state_dir()
        identity = ("shared\0" + credentials.shared_token_file if credentials.shared_token_file
                    else credentials.client_id + "\0" + credentials.client_secret)
        self._identity = hashlib.sha256(identity.encode()).hexdigest()
        self._http = http or httpx.Client(
            timeout=httpx.Timeout(10.0, connect=5.0), follow_redirects=False, trust_env=False,
        )

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _token(self, rejected: str | None = None) -> str:
        if self.credentials.shared_token_file:
            # toss-stock remains the sole token issuer. Never create, copy or
            # refresh a token here: that would revoke its running monitor's token.
            cached = storage.read_json(Path(self.credentials.shared_token_file))
            token, expiry = cached.get("access_token"), cached.get("expires_at", 0)
            if (not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token) or
                    not isinstance(expiry, (int, float)) or not math.isfinite(expiry) or
                    expiry <= time.time() + 5 or token == rejected):
                raise BrokerError(
                    "Shared Toss token is missing, expired or rejected; let toss-stock "
                    "refresh its connection, then retry. Autostock will not issue a token."
                )
            return token
        path = self.state_dir / f"token-{self._identity}.json"
        with storage.locked(path.with_suffix(".lock")):
            cached = storage.read_json(path)
            token = cached.get("access_token")
            expiry = cached.get("expires_at", 0)
            if cached and (not isinstance(token, str) or not token or
                           not isinstance(expiry, (int, float)) or not math.isfinite(expiry)):
                raise BrokerError("Toss token cache is invalid; repair private storage before continuing")
            if token and token != rejected and expiry > time.time() + 60:
                return token
            try:
                response = self._http.post(API_BASE + "/oauth2/token", data={
                    "grant_type": "client_credentials",
                    "client_id": self.credentials.client_id,
                    "client_secret": self.credentials.client_secret,
                }, follow_redirects=False)
            except httpx.HTTPError:
                raise BrokerError("Toss token request failed; credentials were not logged") from None
            if response.status_code != 200:
                raise _api_error(response)
            try:
                result = response.json()
                token = result["access_token"]
                lifetime = float(result["expires_in"])
                if not isinstance(token, str) or not token or not math.isfinite(lifetime) or lifetime <= 60:
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                raise BrokerError("Toss returned an invalid token response") from None
            storage.write_json(path, {"access_token": token, "expires_at": time.time() + lifetime})
            return token

    def request(self, method: str, path: str, *, params=None, body=None, account=False):
        method = method.upper()
        if method not in {"GET", "POST", "DELETE"} or not path.startswith("/api/v1/"):
            raise BrokerError("Unsupported Toss API request")
        if method != "GET" and (self.read_only or self.credentials.shared_token_file):
            raise BrokerError("Toss is read-only; linking credentials does not enable trading")
        if account and not self.credentials.account_seq:
            raise BrokerError("Select a Toss account before account-scoped requests")
        token = self._token()
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            headers = {"Authorization": f"Bearer {token}"}
            if account:
                headers["X-Tossinvest-Account"] = self.credentials.account_seq
            try:
                response = self._http.request(
                    method, API_BASE + path, params=params, json=body, headers=headers,
                    follow_redirects=False,
                )
            except httpx.HTTPError:
                if method == "GET" and attempt + 1 < attempts:
                    time.sleep(0.25 * 2 ** attempt)
                    continue
                raise BrokerError(
                    "Toss request failed; reconcile order status before retrying any write"
                ) from None
            if response.status_code == 401 and method == "GET" and attempt == 0:
                token = self._token(rejected=token)
                continue
            if response.status_code in {429, 500, 502, 503, 504} and attempt + 1 < attempts:
                try:
                    delay = float(response.headers.get("Retry-After", 0.25 * 2 ** attempt))
                except ValueError:
                    delay = 1.0
                # Never sleep indefinitely, or retry sooner than the server allows.
                if not 0 <= delay <= 5:
                    raise _api_error(response)
                time.sleep(delay)
                continue
            if not 200 <= response.status_code < 300:
                raise _api_error(response)
            if response.status_code == 204:
                return None
            try:
                result = response.json()
                return result["result"]
            except (ValueError, KeyError, TypeError):
                raise BrokerError("Toss returned an invalid API response") from None
        raise BrokerError("Toss read retries exhausted")

    def create_order(self, payload: dict) -> dict:
        if self.read_only or self.credentials.shared_token_file:
            raise BrokerError("Toss is read-only; linking credentials does not enable trading")
        key = payload.get("clientOrderId", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,36}", key):
            raise BrokerError("Toss client_order_id must be 1–36 letters, digits, '-' or '_'")
        account = self.credentials.account_seq
        if not account:
            raise BrokerError("No Toss account selected")
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        path = self.state_dir / f"orders-{self._identity}-{account}.json"
        with storage.locked(path.with_suffix(".lock")):
            records = storage.read_json(path)
            previous = records.get(key)
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise BrokerError("Toss client_order_id was already used for a different order")
                if previous.get("response"):
                    return previous["response"]
                raise BrokerError(
                    "Previous Toss submission is unresolved; check Toss order history before "
                    "placing another order. Automatic resubmission is disabled."
                )
            records[key] = {"fingerprint": fingerprint, "submitted_at": time.time(), "response": None}
            storage.write_json(path, records)
            # Persist BEFORE the network call, including before token issuance.
            # Toss forgets its idempotency key after ten minutes; we do not.
            result = self.request("POST", "/api/v1/orders", body=payload, account=True)
            if not isinstance(result, dict) or not result.get("orderId"):
                raise BrokerError("Toss submission result is unresolved; inspect order history")
            records[key]["response"] = result
            storage.write_json(path, records)
            return result

    def accounts(self) -> list[dict]:
        return self.request("GET", "/api/v1/accounts")

    def pages(self, path: str, field: str, *, params=None, account=True) -> list[dict]:
        query = {"limit": 100, **(params or {})}
        rows, seen = [], set()
        for _ in range(1000):
            result = self.request("GET", path, params=query, account=account)
            rows.extend(result[field])
            if not result.get("hasNext"):
                return rows
            cursor = result.get("nextCursor")
            if not cursor or cursor in seen:
                raise BrokerError("Toss pagination did not advance; refusing incomplete account data")
            seen.add(cursor)
            query["cursor"] = cursor
        raise BrokerError("Toss pagination exceeded the bound; refusing incomplete account data")

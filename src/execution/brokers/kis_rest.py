"""Raw KIS OpenAPI REST transport (Korean Investment & Securities).

Why raw REST and not the ``pykis`` SDK: pykis routes market-data to the *real*
domain, so it cannot serve quotes with virtual(모의) app keys alone — and a 모의
PoC account only has virtual keys (verified: EGW02004). Orders/account/quote on the
모의 domain all work with virtual keys over plain REST, so this thin client talks to
the 모의 (or 실전) domain directly.

Secrets (appkey/secret/token) are never logged (SECURITY-03/12).
"""

from __future__ import annotations

import json
import threading
import time

import requests
from loguru import logger

from src.core.exceptions import BrokerError

_REAL_DOMAIN = "https://openapi.koreainvestment.com:9443"
_PAPER_DOMAIN = "https://openapivts.koreainvestment.com:29443"  # 모의투자
_TOKEN_TTL = 23 * 3600  # KIS access token lives ~24h; refresh before that
_TOKEN_REISSUE_GAP = 60  # KIS issues a token at most once per minute (EGW00133)


class KisRestClient:
    """Token-managed, throttled JSON transport for one KIS account/domain."""

    def __init__(
        self,
        appkey: str,
        appsecret: str,
        *,
        paper: bool = True,
        connect_timeout: float = 3.0,
        read_timeout: float = 5.0,
        rate_limit_per_sec: float = 2.0,
    ):
        self._appkey = appkey
        self._appsecret = appsecret
        self._paper = paper
        self._base = _PAPER_DOMAIN if paper else _REAL_DOMAIN
        self._timeout = (connect_timeout, read_timeout)
        self._min_interval = 1.0 / rate_limit_per_sec if rate_limit_per_sec > 0 else 0.0
        self._session = requests.Session()
        self._lock = threading.Lock()
        self._token: str | None = None
        self._token_ts = 0.0
        self._last_issue_attempt = 0.0
        self._last_call = 0.0

    @property
    def paper(self) -> bool:
        return self._paper

    # -- internals ------------------------------------------------------- #
    def _throttle(self) -> None:
        if self._min_interval <= 0:
            return
        wait = self._min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _ensure_token(self) -> str:
        """Lazy token: (re)issue when older than the TTL. Respects KIS's 1/min
        issuance cap — if we cannot reissue yet but hold a token, keep using it;
        only raise when there is no usable token at all (fail-closed)."""
        with self._lock:
            if self._token and (time.time() - self._token_ts) < _TOKEN_TTL:
                return self._token
            if self._token and (time.monotonic() - self._last_issue_attempt) < _TOKEN_REISSUE_GAP:
                return self._token  # too soon to reissue; old token still valid enough
            self._last_issue_attempt = time.monotonic()
            self._throttle()  # the token POST counts against the per-sec cap too
            try:
                resp = self._session.post(
                    self._base + "/oauth2/tokenP",
                    json={
                        "grant_type": "client_credentials",
                        "appkey": self._appkey,
                        "appsecret": self._appsecret,
                    },
                    timeout=self._timeout,
                )
                data = resp.json()
            except Exception as e:  # noqa: BLE001 — network/parse
                if self._token:
                    return self._token
                raise BrokerError(f"KIS token request failed: {e}") from e
            token = data.get("access_token")
            if not token:
                if self._token:
                    logger.warning(f"KIS token reissue declined ({data.get('error_code')}); using existing")
                    return self._token
                raise BrokerError(
                    f"KIS token issuance failed: {data.get('error_description') or data.get('msg1')}"
                )
            self._token = token
            self._token_ts = time.time()
            return token

    def _headers(self, tr_id: str) -> dict[str, str]:
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._ensure_token()}",
            "appkey": self._appkey,
            "appsecret": self._appsecret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    # -- calls ----------------------------------------------------------- #
    def get(self, path: str, tr_id: str, params: dict) -> dict:
        headers = self._headers(tr_id)  # ensure token first (it self-throttles if it issues)
        self._throttle()                # then space the data call from the token POST
        try:
            resp = self._session.get(
                self._base + path, headers=headers, params=params, timeout=self._timeout
            )
            return resp.json()
        except requests.exceptions.RequestException as e:
            raise BrokerError(f"KIS GET {path} failed: {e}") from e

    def post(self, path: str, tr_id: str, body: dict) -> dict:
        headers = self._headers(tr_id)
        self._throttle()
        try:
            resp = self._session.post(
                self._base + path, headers=headers, data=json.dumps(body), timeout=self._timeout
            )
            return resp.json()
        except requests.exceptions.RequestException as e:
            raise BrokerError(f"KIS POST {path} failed: {e}") from e
